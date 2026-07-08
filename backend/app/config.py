from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    supabase_service_role_key: str
    student_id: str = "guhan"

    llm_provider: Literal["openai", "gemini"] = "gemini"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    questions_per_topic: int = 5
    target_questions_per_subject: int = 10
    progress_lookback_days: int = 3
    prompt_version: str = "iep-v1"

    api_host: str = "0.0.0.0"
    api_port: int = 8001
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
