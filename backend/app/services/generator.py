from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.config import get_settings
from app.models import GenerateWorksheetRequest, GenerateWorksheetResult, GeneratedQuestion, TopicProgress
from app.db.supabase_client import get_supabase
from app.services.dedup import (
    fetch_recent_question_texts,
    filter_novel_questions,
    recent_question_hashes,
)
from app.services.llm import generate_worksheet_json
from app.services.math_templates import (
    collect_used_math_signatures,
    generate_math_questions,
    supports_math_topic,
)
from app.services.progress import fetch_recent_topic_progress
from app.services.question_counts import compute_topic_question_counts


def delete_existing_questions(
    student_id: str,
    question_date,
    worksheet_set: int,
    subjects: Optional[List[str]] = None,
) -> int:
    sb = get_supabase()
    query = (
        sb.table("daily_generated_questions")
        .delete()
        .eq("student_id", student_id)
        .eq("question_date", question_date.isoformat())
    )
    try:
        query = query.eq("worksheet_set", worksheet_set)
        if subjects:
            query = query.in_("subject", subjects)
        resp = query.execute()
        return len(resp.data or [])
    except Exception as exc:
        if "worksheet_set" not in str(exc).lower():
            raise
        query = (
            sb.table("daily_generated_questions")
            .delete()
            .eq("student_id", student_id)
            .eq("question_date", question_date.isoformat())
        )
        if subjects:
            query = query.in_("subject", subjects)
        if worksheet_set != 1:
            return 0
        resp = query.execute()
        return len(resp.data or [])


def fetch_existing_questions(
    student_id: str,
    question_date: date,
    worksheet_set: int,
    subjects: Optional[List[str]] = None,
) -> List[dict]:
    sb = get_supabase()
    query = (
        sb.table("daily_generated_questions")
        .select(
            "id, subject, topic, difficulty_level, question_text, scaffolding_hints, "
            "expected_answer, worksheet_set, task_id"
        )
        .eq("student_id", student_id)
        .eq("question_date", question_date.isoformat())
    )
    try:
        query = query.eq("worksheet_set", worksheet_set)
        if subjects:
            query = query.in_("subject", subjects)
        resp = query.execute()
        return resp.data or []
    except Exception as exc:
        if "worksheet_set" not in str(exc).lower():
            raise
        if worksheet_set != 1:
            return []
        query = (
            sb.table("daily_generated_questions")
            .select(
                "id, subject, topic, difficulty_level, question_text, scaffolding_hints, "
                "expected_answer, task_id"
            )
            .eq("student_id", student_id)
            .eq("question_date", question_date.isoformat())
        )
        if subjects:
            query = query.in_("subject", subjects)
        resp = query.execute()
        return resp.data or []


def subjects_needing_generation(
    existing_rows: List[dict],
    progress: List[TopicProgress],
    requested_subjects: Optional[List[str]],
) -> List[str]:
    """Return subjects that still need questions for this date/set."""
    existing_subjects = {str(r.get("subject") or "") for r in existing_rows}
    candidates = requested_subjects or sorted({p.subject for p in progress})
    return [s for s in candidates if s not in existing_subjects]


def _filter_progress(progress, subjects: Optional[List[str]], topics: Optional[List[str]]):
    filtered = progress
    if subjects:
        subject_set = {s.lower() for s in subjects}
        filtered = [p for p in filtered if p.subject.lower() in subject_set]
    if topics:
        topic_set = {t.lower() for t in topics}
        filtered = [p for p in filtered if p.topic.lower() in topic_set]
    return filtered


def insert_generated_questions(
    student_id: str,
    question_date,
    questions: List[GeneratedQuestion],
    task_id_by_topic: dict,
    worksheet_set: int = 1,
) -> int:
    settings = get_settings()
    sb = get_supabase()
    rows = []
    for q in questions:
        key = f"{q.subject}::{q.topic}"
        rows.append(
            {
                "student_id": student_id,
                "question_date": question_date.isoformat(),
                "subject": q.subject,
                "topic": q.topic,
                "difficulty_level": q.difficulty_level,
                "question_text": q.question_text,
                "scaffolding_hints": q.scaffolding_hints,
                "expected_answer": q.expected_answer,
                "task_id": task_id_by_topic.get(key),
                "source_prompt_version": settings.prompt_version,
                "is_assigned_as_chore": worksheet_set == 1,
                "worksheet_set": worksheet_set,
            }
        )
    if not rows:
        return 0
    try:
        sb.table("daily_generated_questions").insert(rows).execute()
    except Exception as exc:
        if "worksheet_set" not in str(exc).lower():
            raise
        for row in rows:
            row.pop("worksheet_set", None)
        sb.table("daily_generated_questions").insert(rows).execute()
    return len(rows)


def _rows_to_generated(rows: List[dict]) -> List[GeneratedQuestion]:
    out: List[GeneratedQuestion] = []
    for row in rows:
        try:
            out.append(
                GeneratedQuestion(
                    subject=row["subject"],
                    topic=row["topic"],
                    difficulty_level=row.get("difficulty_level") or "maintained",
                    question_text=row["question_text"],
                    scaffolding_hints=row.get("scaffolding_hints") or [],
                    expected_answer=row.get("expected_answer") or "",
                )
            )
        except Exception:
            continue
    return out


def _build_questions_for_progress(
    *,
    student_id: str,
    question_date: date,
    progress: List[TopicProgress],
    topic_question_counts: dict,
    avoid_texts: List[str],
) -> List[GeneratedQuestion]:
    """Parametric math + LLM for non-template topics, with dedup filtering."""
    settings = get_settings()
    known_hashes = recent_question_hashes(avoid_texts)
    used_math_sigs = collect_used_math_signatures(
        avoid_texts, [p.topic for p in progress if supports_math_topic(p.topic)]
    )

    math_questions: List[GeneratedQuestion] = []
    llm_progress: List[TopicProgress] = []
    llm_counts: dict = {}

    for tp in progress:
        key = f"{tp.subject}::{tp.topic}"
        count = topic_question_counts.get(key, 0)
        if count <= 0:
            continue
        if supports_math_topic(tp.topic):
            math_questions.extend(
                generate_math_questions(
                    student_id=student_id,
                    question_date=question_date,
                    topic=tp.topic,
                    difficulty=tp.recommended_difficulty,
                    count=count,
                    used_signatures=used_math_sigs,
                )
            )
        else:
            llm_progress.append(tp)
            llm_counts[key] = count

    llm_questions: List[GeneratedQuestion] = []
    if llm_progress:
        avoid = list(avoid_texts)
        retries = max(0, settings.llm_retry_on_duplicates)
        for attempt in range(retries + 1):
            payload = generate_worksheet_json(
                student_id=student_id,
                question_date=question_date.isoformat(),
                topic_progress=llm_progress,
                topic_question_counts=llm_counts,
                avoid_questions=avoid,
            )
            novel = filter_novel_questions(payload.questions, known_hashes)
            llm_questions = novel
            if len(novel) >= sum(llm_counts.values()) or attempt >= retries:
                break
            # Strengthen avoid list with whatever came back and retry once.
            avoid = avoid + [q.question_text for q in payload.questions]

    combined = math_questions + llm_questions
    # Final pass: drop any remaining duplicates against history + within batch.
    return filter_novel_questions(combined, known_hashes)


def generate_and_store_daily_worksheet(
    req: Optional[GenerateWorksheetRequest] = None,
) -> GenerateWorksheetResult:
    settings = get_settings()
    req = req or GenerateWorksheetRequest()
    student_id = req.student_id or settings.student_id
    question_date = req.question_date or date.today()

    progress = fetch_recent_topic_progress(student_id=student_id)
    progress = _filter_progress(progress, req.subjects, req.topics)
    if not progress:
        raise ValueError("No active topics found for generation. Seed tasks table or adjust filters.")

    deleted_count = 0
    skipped_existing = False

    # Capture recent texts before any delete so regenerate cannot clone today's sheet.
    avoid_texts = fetch_recent_question_texts(student_id=student_id)

    if req.replace_existing:
        deleted_count = delete_existing_questions(
            student_id=student_id,
            question_date=question_date,
            worksheet_set=req.worksheet_set,
            subjects=req.subjects,
        )
    elif req.skip_if_exists:
        existing = fetch_existing_questions(
            student_id=student_id,
            question_date=question_date,
            worksheet_set=req.worksheet_set,
            subjects=req.subjects,
        )
        needing = subjects_needing_generation(existing, progress, req.subjects)
        if not needing:
            return GenerateWorksheetResult(
                student_id=student_id,
                question_date=question_date,
                deleted_count=0,
                inserted_count=0,
                skipped_existing=True,
                topic_progress=progress,
                questions=_rows_to_generated(existing),
            )
        # Only generate for subjects that are still empty.
        progress = _filter_progress(progress, needing, req.topics)
        if not progress:
            return GenerateWorksheetResult(
                student_id=student_id,
                question_date=question_date,
                deleted_count=0,
                inserted_count=0,
                skipped_existing=True,
                topic_progress=progress,
                questions=_rows_to_generated(existing),
            )
        skipped_existing = bool(existing)
        req = req.model_copy(update={"subjects": needing})

    if req.difficulty_override:
        # One-shot, applies to every topic in this call only and is never persisted —
        # independent of a topic's persisted `difficulty_pin` (set via
        # POST /topics/{task_id}/difficulty-pin), which the caller already baked into
        # `recommended_difficulty` above. This override simply wins for this one call.
        progress = [
            tp.model_copy(update={"recommended_difficulty": req.difficulty_override})
            for tp in progress
        ]

    topic_question_counts = compute_topic_question_counts(
        progress,
        settings.target_questions_per_subject,
        adaptive=settings.adaptive_question_counts,
    )

    questions = _build_questions_for_progress(
        student_id=student_id,
        question_date=question_date,
        progress=progress,
        topic_question_counts=topic_question_counts,
        avoid_texts=avoid_texts,
    )

    task_id_by_topic = {f"{p.subject}::{p.topic}": p.task_id for p in progress}
    inserted = insert_generated_questions(
        student_id=student_id,
        question_date=question_date,
        questions=questions,
        task_id_by_topic=task_id_by_topic,
        worksheet_set=req.worksheet_set,
    )

    return GenerateWorksheetResult(
        student_id=student_id,
        question_date=question_date,
        deleted_count=deleted_count,
        inserted_count=inserted,
        skipped_existing=skipped_existing,
        topic_progress=progress,
        questions=questions,
    )
