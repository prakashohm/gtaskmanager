from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from app.config import get_settings
from app.db.supabase_client import get_supabase
from app.models import DifficultyLevel, TopicProgress


def difficulty_from_success_rate(rate: float) -> DifficultyLevel:
    if rate < 60.0:
        return "simplified"
    if rate > 80.0:
        return "increased"
    return "maintained"


def _parse_entry_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def weighted_success_rate(
    entries: List[dict],
    *,
    today: Optional[date] = None,
    decay: float = 0.7,
) -> tuple[float, float, float]:
    """
    EWMA-style success rate: each attempt is weighted by decay^days_ago.
    Returns (rate_0_to_100, weighted_correct, weighted_attempts).
    """
    today = today or date.today()
    weighted_correct = 0.0
    weighted_attempts = 0.0
    for row in entries:
        entry_day = _parse_entry_date(row.get("entry_date")) or today
        days_ago = max(0, (today - entry_day).days)
        weight = decay**days_ago
        weighted_attempts += weight
        is_correct = row.get("is_correct") is True
        if row.get("is_correct") is None and row.get("score") is not None:
            is_correct = float(row["score"]) >= 60.0
        if is_correct:
            weighted_correct += weight
    if weighted_attempts <= 0:
        return 0.0, 0.0, 0.0
    rate = (weighted_correct / weighted_attempts) * 100.0
    return rate, weighted_correct, weighted_attempts


def fetch_recent_topic_progress(
    student_id: Optional[str] = None,
    lookback_days: Optional[int] = None,
) -> List[TopicProgress]:
    """Aggregate success rates per topic from worksheet_entries over the last N days."""
    settings = get_settings()
    student_id = student_id or settings.student_id
    lookback_days = lookback_days or settings.progress_lookback_days
    since = date.today() - timedelta(days=lookback_days - 1)
    decay = settings.progress_ewma_decay

    sb = get_supabase()
    entries_resp = (
        sb.table("worksheet_entries")
        .select("task_id, subject, topic, is_correct, score, entry_date")
        .eq("student_id", student_id)
        .gte("entry_date", since.isoformat())
        .execute()
    )
    entries = entries_resp.data or []

    tasks_resp = (
        sb.table("tasks")
        .select("id, subject, topic")
        .eq("student_id", student_id)
        .eq("is_active", True)
        .execute()
    )
    active_tasks = tasks_resp.data or []

    stats: dict = {}
    for task in active_tasks:
        key = f"{task['subject']}::{task['topic']}"
        stats[key] = {
            "subject": task["subject"],
            "topic": task["topic"],
            "task_id": task["id"],
            "attempts": 0,
            "correct": 0,
            "entries": [],
        }

    for row in entries:
        key = f"{row['subject']}::{row['topic']}"
        if key not in stats:
            stats[key] = {
                "subject": row["subject"],
                "topic": row["topic"],
                "task_id": row.get("task_id"),
                "attempts": 0,
                "correct": 0,
                "entries": [],
            }
        stats[key]["attempts"] += 1
        stats[key]["entries"].append(row)
        if row.get("is_correct") is True:
            stats[key]["correct"] += 1
        elif row.get("is_correct") is None and row.get("score") is not None:
            if float(row["score"]) >= 60.0:
                stats[key]["correct"] += 1

    progress: List[TopicProgress] = []
    for item in stats.values():
        attempts = item["attempts"]
        correct = item["correct"]
        if attempts == 0:
            # New / unpracticed topics start simplified — not mid-band.
            rate = 0.0
            difficulty: DifficultyLevel = "simplified"
        else:
            rate, _, _ = weighted_success_rate(item["entries"], decay=decay)
            difficulty = difficulty_from_success_rate(rate)
        progress.append(
            TopicProgress(
                subject=item["subject"],
                topic=item["topic"],
                task_id=item.get("task_id"),
                attempts=attempts,
                correct=correct,
                success_rate=round(rate, 1),
                recommended_difficulty=difficulty,
            )
        )
    return sorted(progress, key=lambda p: (p.subject.lower(), p.topic.lower()))
