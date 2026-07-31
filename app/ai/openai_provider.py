"""OpenAI provider for course generation.

Placeholder implementation of :class:`CourseGenerationAI` that stores
the target model name and OpenAI client. API integration will be added
in a later PR.
"""

from __future__ import annotations

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[misc, assignment]

from app.ai.interfaces import (
    LessonGenerationRequest,
    LessonGenerationResult,
)


class OpenAICourseGenerationAI:
    """OpenAI-backed implementation of :class:`CourseGenerationAI`."""

    def __init__(self, model: str) -> None:
        if OpenAI is None:
            raise RuntimeError(
                "OpenAI SDK is not installed."
            )
        self._client = OpenAI()
        self._model = model

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Generate or refine lessons via OpenAI."""
        raise NotImplementedError(
            "OpenAI integration is not implemented yet."
        )
