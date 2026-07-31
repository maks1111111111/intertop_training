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
from app.ai.prompt_builder import PromptBuilder


class OpenAICourseGenerationAI:
    """OpenAI-backed implementation of :class:`CourseGenerationAI`."""

    def __init__(
        self,
        model: str,
        client: Optional[AIClient] = None,
        prompt_builder: Optional[PromptBuilder] = None,
    ) -> None:
        self._model = model
        self._client = client if client is not None else DummyAIClient()
        self._prompt_builder = (
            prompt_builder if prompt_builder is not None else PromptBuilder()
        )

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Generate or refine lessons via OpenAI."""
        prompt = self._prompt_builder.build_lesson_generation_prompt(request)
        response = self._client.generate(prompt)
        raise NotImplementedError(
            "Lesson parsing is not implemented yet."
        )
