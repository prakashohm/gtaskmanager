from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

from supabase import Client, create_client

from app.config import get_settings


def normalize_supabase_url(url: str) -> str:
    """Supabase client expects the project root URL, not /rest/v1."""
    cleaned = (url or "").strip()
    if not cleaned:
        return cleaned
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    cleaned = cleaned.rstrip("/")
    cleaned = re.sub(r"/rest/v1/?$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.rstrip("/")


def supabase_host(url: str) -> str:
    return urlparse(normalize_supabase_url(url)).netloc or ""


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    url = normalize_supabase_url(settings.supabase_url)
    if not url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL (project root only, no /rest/v1) "
            "and SUPABASE_SERVICE_ROLE_KEY on the server."
        )
    return create_client(url, settings.supabase_service_role_key)


def check_supabase_connection() -> tuple[bool, str | None]:
    try:
        get_supabase().table("tasks").select("id").limit(1).execute()
        return True, None
    except Exception as exc:
        message = str(exc)
        if "PGRST125" in message or "Invalid path" in message:
            return False, (
                "Invalid Supabase URL. Use the project root only, e.g. "
                "https://YOUR_PROJECT.supabase.co — do not include /rest/v1."
            )
        return False, message
