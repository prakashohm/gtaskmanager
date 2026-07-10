from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, timedelta
from typing import Iterable, List, Optional, Sequence, Set

from app.config import get_settings
from app.db.supabase_client import get_supabase
from app.models import GeneratedQuestion


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")
_DIGIT_SPACE_RE = re.compile(r"(?<=\d)\s+(?=\d)")


def normalize_question_text(text: str) -> str:
    """Normalize question text for near-duplicate comparison."""
    cleaned = unicodedata.normalize("NFKC", text or "")
    cleaned = cleaned.lower().strip()
    cleaned = _PUNCT_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    # Treat "4 x 5" and "4x5" as the same after punctuation removal.
    cleaned = cleaned.replace(" x ", "x")
    cleaned = _DIGIT_SPACE_RE.sub("", cleaned)
    return cleaned


def question_text_hash(text: str) -> str:
    return hashlib.sha256(normalize_question_text(text).encode("utf-8")).hexdigest()


def fetch_recent_question_texts(
    student_id: Optional[str] = None,
    lookback_days: Optional[int] = None,
    exclude_date: Optional[date] = None,
) -> List[str]:
    """Return recent question texts used for anti-repeat prompting and filtering."""
    settings = get_settings()
    student_id = student_id or settings.student_id
    lookback_days = lookback_days or settings.dedup_lookback_days
    since = date.today() - timedelta(days=lookback_days - 1)

    sb = get_supabase()
    query = (
        sb.table("daily_generated_questions")
        .select("question_text, question_date")
        .eq("student_id", student_id)
        .gte("question_date", since.isoformat())
        .order("question_date", desc=True)
    )
    resp = query.execute()
    rows = resp.data or []
    texts: List[str] = []
    seen: Set[str] = set()
    for row in rows:
        if exclude_date and row.get("question_date") == exclude_date.isoformat():
            continue
        text = (row.get("question_text") or "").strip()
        if not text:
            continue
        key = question_text_hash(text)
        if key in seen:
            continue
        seen.add(key)
        texts.append(text)
    return texts


def recent_question_hashes(texts: Sequence[str]) -> Set[str]:
    return {question_text_hash(t) for t in texts if t}


def is_duplicate_question(text: str, known_hashes: Set[str]) -> bool:
    return question_text_hash(text) in known_hashes


def filter_novel_questions(
    questions: Iterable[GeneratedQuestion],
    known_hashes: Set[str],
) -> List[GeneratedQuestion]:
    """Drop questions that match known hashes; also dedupe within the batch."""
    kept: List[GeneratedQuestion] = []
    batch_hashes: Set[str] = set()
    for q in questions:
        h = question_text_hash(q.question_text)
        if h in known_hashes or h in batch_hashes:
            continue
        batch_hashes.add(h)
        kept.append(q)
    return kept


def param_signature_hash(topic: str, signature: str) -> str:
    payload = f"{normalize_question_text(topic)}::{normalize_question_text(signature)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
