from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import GenerateWorksheetRequest, GenerateWorksheetResult, TopicProgress
from app.services.generator import generate_and_store_daily_worksheet
from app.services.progress import fetch_recent_topic_progress

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
    llm_ready = bool(
        (s.llm_provider == "gemini" and s.gemini_api_key)
        or (s.llm_provider == "openai" and s.openai_api_key)
    )
    return {"status": "ok", "llm_provider": s.llm_provider, "llm_ready": llm_ready}


def _ensure_llm_configured() -> None:
    s = get_settings()
    if s.llm_provider == "gemini" and not s.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to backend/.env from "
            "https://aistudio.google.com/apikey then restart the backend."
        )
    if s.llm_provider == "openai" and not s.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to backend/.env or set LLM_PROVIDER=gemini."
        )


@app.get("/progress/{student_id}", response_model=List[TopicProgress])
def get_progress(
    student_id: str, lookback_days: Optional[int] = None
) -> List[TopicProgress]:
    return fetch_recent_topic_progress(student_id=student_id, lookback_days=lookback_days)


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
        raise HTTPException(status_code=500, detail=f"Worksheet generation failed: {exc}") from exc


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)
