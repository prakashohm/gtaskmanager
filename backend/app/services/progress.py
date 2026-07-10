from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from app.config import get_settings
from app.db.supabase_client import get_supabase
from app.models import DifficultyLevel, TopicProgress

_DIFFICULTY_LEVELS: List[DifficultyLevel] = ["simplified", "maintained", "increased"]


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


def apply_hysteresis(
    raw_difficulty: DifficultyLevel,
    current_adaptive_difficulty: Optional[DifficultyLevel],
    rate: float,
    margin: float = 5.0,
) -> tuple[DifficultyLevel, bool, str]:
    """
    Only accept a difficulty change once the success rate clears the relevant
    60%/80% threshold by `margin` points, so a topic hovering right at a
    boundary doesn't flip difficulty back and forth day to day.

    Returns (effective_difficulty, changed, rationale). `changed` is True when
    the caller should persist `effective_difficulty` as the new
    current_adaptive_difficulty (either this is the first time we're tracking
    this topic, or the margin was actually cleared).
    """
    if current_adaptive_difficulty is None:
        return raw_difficulty, True, ""
    if raw_difficulty == current_adaptive_difficulty:
        return current_adaptive_difficulty, False, ""

    current_idx = _DIFFICULTY_LEVELS.index(current_adaptive_difficulty)
    raw_idx = _DIFFICULTY_LEVELS.index(raw_difficulty)

    if raw_idx > current_idx:
        boundary = 60.0 if current_adaptive_difficulty == "simplified" else 80.0
        required = boundary + margin
        if rate >= required:
            return (
                raw_difficulty,
                True,
                f"Moved to {raw_difficulty} — {rate:.0f}% cleared the {required:.0f}% bar.",
            )
        short_by = round(required - rate, 1)
        return (
            current_adaptive_difficulty,
            False,
            f"Holding at {current_adaptive_difficulty} — {short_by}pt short of the "
            f"{required:.0f}% needed to move up.",
        )

    boundary = 80.0 if current_adaptive_difficulty == "increased" else 60.0
    required = boundary - margin
    if rate <= required:
        return (
            raw_difficulty,
            True,
            f"Moved to {raw_difficulty} — {rate:.0f}% dropped below the {required:.0f}% bar.",
        )
    short_by = round(rate - required, 1)
    return (
        current_adaptive_difficulty,
        False,
        f"Holding at {current_adaptive_difficulty} — {short_by}pt above the "
        f"{required:.0f}% threshold to move down.",
    )


def resolve_topic_difficulty(
    raw_difficulty: DifficultyLevel,
    current_adaptive_difficulty: Optional[DifficultyLevel],
    rate: float,
    *,
    pin: Optional[DifficultyLevel] = None,
    margin: float = 5.0,
    is_new_topic: bool = False,
) -> tuple[DifficultyLevel, bool, str]:
    """Resolve the effective difficulty for a topic: a manual pin always wins;
    otherwise hysteresis decides whether to accept the raw recommendation.

    Returns (effective_difficulty, changed, rationale) — `changed` mirrors
    apply_hysteresis and is always False when a pin is active (a pin isn't
    "learned" adaptive state, so there's nothing to persist).
    """
    if pin is not None:
        return pin, False, "Pinned by parent."
    difficulty, changed, rationale = apply_hysteresis(raw_difficulty, current_adaptive_difficulty, rate, margin)
    if not rationale:
        rationale = (
            "New topic — starting simplified."
            if is_new_topic
            else f"{difficulty} — {rate:.0f}% recent success."
        )
    return difficulty, changed, rationale


def compute_trend(
    entries: List[dict],
    full_rate: float,
    *,
    today: Optional[date] = None,
    trend_window_days: int = 3,
    decay: float = 0.7,
    min_recent_attempts: int = 2,
) -> tuple[Optional[str], Optional[float]]:
    """Compare a short recent sub-window against the full lookback rate."""
    today = today or date.today()
    recent_entries = [
        row
        for row in entries
        if max(0, (today - (_parse_entry_date(row.get("entry_date")) or today)).days) < trend_window_days
    ]
    if len(recent_entries) < min_recent_attempts:
        return None, None
    recent_rate, _, _ = weighted_success_rate(recent_entries, today=today, decay=decay)
    delta = round(recent_rate - full_rate, 1)
    if abs(delta) < 5.0:
        return "steady", delta
    return ("improving" if delta > 0 else "declining"), delta


def _fetch_active_tasks(sb, student_id: str) -> tuple[List[dict], bool]:
    """Returns (rows, hysteresis_columns_available)."""
    try:
        resp = (
            sb.table("tasks")
            .select("id, subject, topic, difficulty_pin, current_adaptive_difficulty")
            .eq("student_id", student_id)
            .eq("is_active", True)
            .execute()
        )
        return resp.data or [], True
    except Exception:
        resp = (
            sb.table("tasks")
            .select("id, subject, topic")
            .eq("student_id", student_id)
            .eq("is_active", True)
            .execute()
        )
        return resp.data or [], False


def _persist_adaptive_difficulty(sb, task_id: str, difficulty: DifficultyLevel, today: date) -> None:
    try:
        sb.table("tasks").update(
            {"current_adaptive_difficulty": difficulty, "difficulty_changed_at": today.isoformat()}
        ).eq("id", task_id).execute()
    except Exception:
        pass  # Columns not migrated yet — hysteresis just won't persist until they are.


def set_topic_difficulty_pin(task_id: str, difficulty_pin: Optional[DifficultyLevel]) -> None:
    """Persist (or clear, when None) a parent's manual difficulty pin for one topic."""
    sb = get_supabase()
    sb.table("tasks").update({"difficulty_pin": difficulty_pin}).eq("id", task_id).execute()


def fetch_recent_worksheet_entries(
    student_id: str,
    *,
    subject: Optional[str] = None,
    topic: Optional[str] = None,
    limit: int = 20,
) -> List[dict]:
    """Read-only audit trail: recent answered questions, newest first."""
    sb = get_supabase()
    query = (
        sb.table("worksheet_entries")
        .select("subject, topic, question_text, student_answer, expected_answer, is_correct, entry_date, completed_at")
        .eq("student_id", student_id)
    )
    if subject:
        query = query.eq("subject", subject)
    if topic:
        query = query.eq("topic", topic)
    resp = query.order("entry_date", desc=True).order("completed_at", desc=True).limit(limit).execute()
    return resp.data or []


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
    margin = settings.difficulty_hysteresis_margin
    trend_window_days = settings.trend_window_days
    today = date.today()

    sb = get_supabase()
    entries_resp = (
        sb.table("worksheet_entries")
        .select("task_id, subject, topic, is_correct, score, entry_date")
        .eq("student_id", student_id)
        .gte("entry_date", since.isoformat())
        .execute()
    )
    entries = entries_resp.data or []

    active_tasks, hysteresis_available = _fetch_active_tasks(sb, student_id)

    stats: dict = {}
    for task in active_tasks:
        key = f"{task['subject']}::{task['topic']}"
        stats[key] = {
            "subject": task["subject"],
            "topic": task["topic"],
            "task_id": task["id"],
            "difficulty_pin": task.get("difficulty_pin"),
            "current_adaptive_difficulty": task.get("current_adaptive_difficulty"),
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
                "difficulty_pin": None,
                "current_adaptive_difficulty": None,
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
        task_id = item.get("task_id")
        pin: Optional[DifficultyLevel] = item.get("difficulty_pin")
        current_adaptive: Optional[DifficultyLevel] = item.get("current_adaptive_difficulty")

        if attempts == 0:
            rate = 0.0
            raw_difficulty: DifficultyLevel = "simplified"
        else:
            rate, _, _ = weighted_success_rate(item["entries"], today=today, decay=decay)
            raw_difficulty = difficulty_from_success_rate(rate)

        trend: Optional[str] = None
        trend_delta: Optional[float] = None
        if attempts > 0:
            trend, trend_delta = compute_trend(
                item["entries"], rate, today=today, trend_window_days=trend_window_days, decay=decay
            )

        if hysteresis_available and task_id:
            difficulty, changed, rationale = resolve_topic_difficulty(
                raw_difficulty, current_adaptive, rate, pin=pin, margin=margin, is_new_topic=(attempts == 0)
            )
            if changed:
                _persist_adaptive_difficulty(sb, task_id, difficulty, today)
        elif pin is not None:
            difficulty, rationale = pin, "Pinned by parent."
        else:
            difficulty = raw_difficulty
            rationale = (
                "New topic — starting simplified."
                if attempts == 0
                else f"{difficulty} — {rate:.0f}% recent success."
            )

        progress.append(
            TopicProgress(
                subject=item["subject"],
                topic=item["topic"],
                task_id=task_id,
                attempts=attempts,
                correct=correct,
                success_rate=round(rate, 1),
                recommended_difficulty=difficulty,
                difficulty_pin=pin,
                trend=trend,
                trend_delta=trend_delta,
                rationale=rationale,
            )
        )
    return sorted(progress, key=lambda p: (p.subject.lower(), p.topic.lower()))
