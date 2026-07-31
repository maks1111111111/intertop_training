"""OpenAI provider for course generation.

Placeholder implementation of :class:`CourseGenerationAI` that stores
the target model name and OpenAI client. API integration will be added
in a later PR.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient, DummyAIClient
from app.ai.interfaces import (
    LessonGenerationRequest,
    LessonGenerationResult,
)


class OpenAICourseGenerationAI:
    """OpenAI-backed implementation of :class:`CourseGenerationAI`."""

    def __init__(
        self,
        model: str,
        client: Optional[AIClient] = None,
    ) -> None:
        self._model = model
        self._client = client if client is not None else DummyAIClient()

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Generate or refine lessons via OpenAI."""
        raise NotImplementedError(
            "OpenAI integration is not implemented yet."
        )
