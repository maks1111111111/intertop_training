"""Mock AI provider for course generation.

Returns input lessons unchanged. Used for testing and as a no-op
placeholder until a real AI backend is connected.
"""

from __future__ import annotations

from app.ai.interfaces import (
    LessonGenerationRequest,
    LessonGenerationResult,
)


class MockCourseGenerationAI:
    """Pass-through implementation of :class:`CourseGenerationAI`."""

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Return the request lessons without modification."""
        return LessonGenerationResult(lessons=request.lessons)
