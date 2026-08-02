"""AI provider interfaces for course generation.

Defines request/result models and the protocol that all AI backends
must implement. No concrete providers are included here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from app.content.lesson_builder import LessonCandidate


@dataclass(frozen=True)
class GeneratedCourseMetadata:
    """Structured course metadata parsed from an AI response."""

    language: str
    title: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class LessonGenerationRequest:
    """Input for AI lesson generation."""

    lessons: list[LessonCandidate]


@dataclass(frozen=True)
class LessonGenerationResult:
    """Output from AI lesson generation."""

    lessons: list[LessonCandidate]
    course: Optional[GeneratedCourseMetadata] = None


class CourseGenerationAI(Protocol):
    """Protocol for AI backends that refine or generate lesson content."""

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Generate or refine lessons from the given request."""
        ...
