"""AI service layer for course generation.

Provides a single entry point for lesson generation that delegates to
a pluggable :class:`CourseGenerationAI` provider.
"""

from __future__ import annotations

from app.ai.interfaces import (
    CourseGenerationAI,
    LessonGenerationRequest,
    LessonGenerationResult,
)


class CourseGenerationService:
    """Application service that delegates lesson generation to an AI provider."""

    def __init__(self, provider: CourseGenerationAI) -> None:
        self._provider = provider

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Generate or refine lessons via the configured AI provider."""
        return self._provider.generate_lessons(request)
