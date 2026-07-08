from __future__ import annotations

from datetime import date
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


class GenerateWorksheetResult(BaseModel):
    student_id: str
    question_date: date
    deleted_count: int = 0
    inserted_count: int
    topic_progress: List[TopicProgress]
    questions: List[GeneratedQuestion]
