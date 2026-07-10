from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.supabase_client import check_supabase_connection, supabase_host
from app.models import (
    GenerateWorksheetRequest,
    GenerateWorksheetResult,
    SetDifficultyPinRequest,
    TopicProgress,
    WorksheetEntryRecord,
)
from app.services.generator import generate_and_store_daily_worksheet
from app.services.progress import (
    fetch_recent_topic_progress,
    fetch_recent_worksheet_entries,
    set_topic_difficulty_pin,
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


@app.post("/generate", response_model=GenerateWorksheetResult)
def generate_worksheet(
    body: Optional[GenerateWorksheetRequest] = None,
) -> GenerateWorksheetResult:
    try:
        _ensure_llm_configured()
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
