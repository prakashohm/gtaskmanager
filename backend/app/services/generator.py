from __future__ import annotations

from typing import List, Optional

from app.config import get_settings
from app.models import GenerateWorksheetRequest, GenerateWorksheetResult, GeneratedQuestion
from app.db.supabase_client import get_supabase
from app.services.llm import generate_worksheet_json
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


def generate_and_store_daily_worksheet(
    req: Optional[GenerateWorksheetRequest] = None,
) -> GenerateWorksheetResult:
    from datetime import date

    settings = get_settings()
    req = req or GenerateWorksheetRequest()
    student_id = req.student_id or settings.student_id
    question_date = req.question_date or date.today()

    progress = fetch_recent_topic_progress(student_id=student_id)
    progress = _filter_progress(progress, req.subjects, req.topics)
    if not progress:
        raise ValueError("No active topics found for generation. Seed tasks table or adjust filters.")

    if req.difficulty_override:
        progress = [
            tp.model_copy(update={"recommended_difficulty": req.difficulty_override})
            for tp in progress
        ]

    topic_question_counts = compute_topic_question_counts(
        progress, settings.target_questions_per_subject
    )

    deleted_count = 0
    if req.replace_existing:
        deleted_count = delete_existing_questions(
            student_id=student_id,
            question_date=question_date,
            worksheet_set=req.worksheet_set,
            subjects=req.subjects,
        )

    llm_payload = generate_worksheet_json(
        student_id=student_id,
        question_date=question_date.isoformat(),
        topic_progress=progress,
        topic_question_counts=topic_question_counts,
    )

    task_id_by_topic = {f"{p.subject}::{p.topic}": p.task_id for p in progress}
    inserted = insert_generated_questions(
        student_id=student_id,
        question_date=question_date,
        questions=llm_payload.questions,
        task_id_by_topic=task_id_by_topic,
        worksheet_set=req.worksheet_set,
    )

    return GenerateWorksheetResult(
        student_id=student_id,
        question_date=question_date,
        deleted_count=deleted_count,
        inserted_count=inserted,
        topic_progress=progress,
        questions=llm_payload.questions,
    )
