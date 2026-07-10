from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    supabase_service_role_key: str
    student_id: str = "guhan"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Optional automatic fallback — only used if Claude is rate-limited,
    # overloaded, out of credits, or unreachable. Not a manual provider switch.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    questions_per_topic: int = 5
    target_questions_per_subject: int = 10
    progress_lookback_days: int = 7
    progress_ewma_decay: float = 0.7
    dedup_lookback_days: int = 21
    adaptive_question_counts: bool = True
    llm_retry_on_duplicates: int = 1
    prompt_version: str = "iep-v2-adaptive"

    # Percentage points a success rate must clear a 60%/80% threshold by before
    # the adaptive difficulty is allowed to change (avoids daily flip-flopping
    # for topics hovering right at a boundary).
    difficulty_hysteresis_margin: float = 5.0
    # Size of the "recent" sub-window (in days) used to compute trend vs. the
    # full progress_lookback_days window.
    trend_window_days: int = 3

    api_host: str = "0.0.0.0"
    api_port: int = 8001
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
