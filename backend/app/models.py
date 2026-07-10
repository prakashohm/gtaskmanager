from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


DifficultyLevel = Literal["simplified", "maintained", "increased"]


class GeneratedQuestion(BaseModel):
    subject: str = Field(..., description="e.g. Math, Reading")
    topic: str = Field(..., description="e.g. calculating area, unit price, identifying theme")
    difficulty_level: DifficultyLevel
    question_text: str
    scaffolding_hints: List[str] = Field(default_factory=list)
    expected_answer: str


class DailyWorksheetResponse(BaseModel):
    student_id: str
    question_date: date
    questions: List[GeneratedQuestion]


class TopicProgress(BaseModel):
    subject: str
    topic: str
    task_id: Optional[str] = None
    attempts: int = 0
    correct: int = 0
    success_rate: float = Field(0.0, ge=0.0, le=100.0)
    recommended_difficulty: DifficultyLevel = "maintained"
    difficulty_pin: Optional[DifficultyLevel] = Field(
        None, description="Parent-set manual override; when set, this always wins."
    )
    trend: Optional[Literal["improving", "declining", "steady"]] = Field(
        None, description="Recent-window rate vs. full-window rate; None if too little recent data."
    )
    trend_delta: Optional[float] = Field(
        None, description="Percentage-point delta driving `trend` (recent minus full-window rate)."
    )
    rationale: str = Field(
        "", description="Short human-readable explanation of why recommended_difficulty is what it is."
    )


class GenerateWorksheetRequest(BaseModel):
    student_id: Optional[str] = None
    question_date: Optional[date] = None
    subjects: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    worksheet_set: int = Field(1, ge=1, description="Worksheet round for the day (1=required chore, 2+=bonus)")
    difficulty_override: Optional[DifficultyLevel] = Field(
        None,
        description="One-time parent override for this generation only; omit for fully adaptive",
    )
    replace_existing: bool = Field(
        False,
        description="When true, delete existing questions for this date/set/subjects before inserting",
    )
    skip_if_exists: bool = Field(
        True,
        description="When true and replace_existing is false, skip subjects that already have questions for this date/set",
    )


class GenerateWorksheetResult(BaseModel):
    student_id: str
    question_date: date
    deleted_count: int = 0
    inserted_count: int
    skipped_existing: bool = False
    topic_progress: List[TopicProgress]
    questions: List[GeneratedQuestion]


class SetDifficultyPinRequest(BaseModel):
    student_id: str
    difficulty_pin: Optional[DifficultyLevel] = Field(
        None, description="Set to null/omit to clear the pin and return to fully adaptive."
    )


class WorksheetEntryRecord(BaseModel):
    subject: str
    topic: str
    question_text: Optional[str] = None
    student_answer: Optional[str] = None
    expected_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    entry_date: date
    completed_at: Optional[datetime] = None
