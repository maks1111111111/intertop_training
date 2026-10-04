"""Course-related API response models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CourseSummaryDTO(BaseModel):
    """Published course summary for list responses."""

    slug: str
    title: str
    description: str


class CourseListDTO(BaseModel):
    """List of published course summaries."""

    items: list[CourseSummaryDTO]


class LessonSummaryDTO(BaseModel):
    """Lesson metadata exposed by the HTTP API."""

    id: str
    title: str
    order: int


class CourseDetailDTO(BaseModel):
    """Published course detail for single-course responses."""

    slug: str
    title: str
    description: str
    language: str
    lessons: list[LessonSummaryDTO]


class LessonDetailDTO(BaseModel):
    """Full published lesson content for read-only API consumers."""

    id: str
    title: str
    order: int
    content: str
    practical_task: str
    checklist: list[str]
    common_mistakes: list[str]
    key_takeaways: list[str]
    application_tips: list[str]
    previous_lesson_id: Optional[str] = None
    next_lesson_id: Optional[str] = None
    is_first: bool = False
    is_last: bool = False
