from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.supabase_client import check_supabase_connection, supabase_host
from app.models import (
    CheckAnswerRequest,
    CheckAnswerResponse,
    GenerateWorksheetRequest,
    GenerateWorksheetResult,
    SetDifficultyPinRequest,
    TopicProgress,
    TutorMessageRequest,
    TutorMessageResponse,
    WorksheetEntryRecord,
)
from app.services.generator import generate_and_store_daily_worksheet
from app.services.progress import (
    fetch_recent_topic_progress,
    fetch_recent_worksheet_entries,
    set_topic_difficulty_pin,
)
from app.services.tutor import (
    answers_match,
    check_direct_answer,
    fetch_question_for_tutor,
    generate_tutor_reply,
    log_tutor_attempt_entry,
    log_tutor_solved_entry,
    message_looks_like_answer,
)

app = FastAPI(
    title="Guhan IEP Worksheet Generator",
    description="Adaptive daily worksheet generation with Supabase + LLM",
    version="1.0.0",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    claude_ready = bool(s.anthropic_api_key)
    gemini_fallback_ready = bool(s.gemini_api_key)
    supabase_ok, supabase_error = check_supabase_connection()
    return {
        "status": "ok" if supabase_ok and (claude_ready or gemini_fallback_ready) else "degraded",
        "llm_provider": "claude",
        "llm_model": s.anthropic_model,
        "llm_ready": claude_ready,
        "gemini_fallback_ready": gemini_fallback_ready,
        "supabase_host": supabase_host(s.supabase_url),
        "supabase_ok": supabase_ok,
        "supabase_error": supabase_error,
    }


def _ensure_llm_configured() -> None:
    s = get_settings()
    if not s.anthropic_api_key and not s.gemini_api_key:
        raise RuntimeError(
            "No LLM configured. Set ANTHROPIC_API_KEY (from "
            "https://console.anthropic.com/settings/keys) — optionally also set "
            "GEMINI_API_KEY as an automatic fallback if Claude is unavailable."
        )


@app.get("/progress/{student_id}", response_model=List[TopicProgress])
def get_progress(
    student_id: str, lookback_days: Optional[int] = None
) -> List[TopicProgress]:
    try:
        return fetch_recent_topic_progress(student_id=student_id, lookback_days=lookback_days)
    except Exception as exc:
        detail = str(exc)
        if "PGRST125" in detail or "Invalid path" in detail:
            detail = (
                "Supabase URL is misconfigured on the server. "
                "Set SUPABASE_URL to https://YOUR_PROJECT.supabase.co (no /rest/v1)."
            )
        raise HTTPException(status_code=500, detail=detail) from exc


@app.post("/topics/{task_id}/difficulty-pin")
def set_difficulty_pin(task_id: str, body: SetDifficultyPinRequest) -> dict:
    try:
        set_topic_difficulty_pin(task_id, body.difficulty_pin)
        return {"task_id": task_id, "difficulty_pin": body.difficulty_pin}
    except Exception as exc:
        detail = str(exc)
        if "difficulty_pin" in detail.lower():
            detail = (
                "Could not save the pin — is backend/sql/003_difficulty_controls.sql "
                "applied in Supabase yet? Details: " + detail
            )
        raise HTTPException(status_code=500, detail=detail) from exc


@app.get("/entries/{student_id}", response_model=List[WorksheetEntryRecord])
def get_entries(
    student_id: str,
    subject: Optional[str] = None,
    topic: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> List[WorksheetEntryRecord]:
    try:
        rows = fetch_recent_worksheet_entries(student_id, subject=subject, topic=topic, limit=limit)
        return [WorksheetEntryRecord.model_validate(row) for row in rows]
    except Exception as exc:
        detail = str(exc)
        if "PGRST125" in detail or "Invalid path" in detail:
            detail = (
                "Supabase URL is misconfigured on the server. "
                "Set SUPABASE_URL to https://YOUR_PROJECT.supabase.co (no /rest/v1)."
            )
        raise HTTPException(status_code=500, detail=detail) from exc


@app.post("/tutor/check-answer", response_model=CheckAnswerResponse)
def tutor_check_answer(body: CheckAnswerRequest) -> CheckAnswerResponse:
    """Fast path: grade a typed answer without opening a tutor chat turn."""
    try:
        question_row = fetch_question_for_tutor(body.question_id)
        if not question_row:
            raise HTTPException(status_code=404, detail="Question not found.")
        expected = question_row.get("expected_answer") or ""
        response = check_direct_answer(expected_answer=expected, student_answer=body.answer)
        log_tutor_attempt_entry(
            student_id=body.student_id,
            question_row=question_row,
            student_message=body.answer,
            is_correct=response.correct,
            hint_count=0,
        )
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tutor/message", response_model=TutorMessageResponse)
def tutor_message(body: TutorMessageRequest) -> TutorMessageResponse:
    try:
        question_row = fetch_question_for_tutor(body.question_id)
        if not question_row:
            raise HTTPException(status_code=404, detail="Question not found.")
        expected = question_row.get("expected_answer") or ""
        # Deterministic correct answers skip the LLM entirely.
        if answers_match(body.message, expected):
            response = TutorMessageResponse(
                reply="Yes! That's exactly right — nice work.", solved=True
            )
        else:
            _ensure_llm_configured()
            response = generate_tutor_reply(
                question_text=question_row["question_text"],
                topic=question_row["topic"],
                difficulty=question_row.get("difficulty_level") or "maintained",
                expected_answer=expected,
                history=body.history,
                student_message=body.message,
            )
        hint_count = sum(1 for turn in body.history if turn.role == "tutor")
        if response.solved:
            log_tutor_solved_entry(
                student_id=body.student_id,
                question_row=question_row,
                student_message=body.message,
                hint_count=hint_count,
            )
        elif message_looks_like_answer(body.message):
            log_tutor_attempt_entry(
                student_id=body.student_id,
                question_row=question_row,
                student_message=body.message,
                is_correct=False,
                hint_count=hint_count,
            )
        return response
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/generate", response_model=GenerateWorksheetResult)
def generate_worksheet(
    body: Optional[GenerateWorksheetRequest] = None,
) -> GenerateWorksheetResult:
    try:
        # Template-backed topics no longer require an LLM key.
        return generate_and_store_daily_worksheet(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc)
        if "PGRST125" in detail or "Invalid path" in detail:
            detail = (
                "Supabase URL is misconfigured on the server. "
                "Set SUPABASE_URL to https://YOUR_PROJECT.supabase.co (no /rest/v1)."
            )
        raise HTTPException(status_code=500, detail=detail) from exc


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)
