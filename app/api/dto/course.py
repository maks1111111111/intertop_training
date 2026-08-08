"""Course-related API response models."""

from __future__ import annotations

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
