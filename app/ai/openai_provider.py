"""OpenAI provider for course generation.

Implementation of :class:`CourseGenerationAI` that wires together a
prompt builder, AI client, and response parser. Full OpenAI course
generation is not complete until response parsing is implemented.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient, DummyAIClient
from app.ai.config import OpenAIConfig
from app.ai.interfaces import (
    LessonGenerationRequest,
    LessonGenerationResult,
)
from app.ai.openai_client import OpenAIClient
from app.ai.prompt_builder import PromptBuilder
from app.ai.response_parser import AIResponseParser


class OpenAICourseGenerationAI:
    """OpenAI-backed implementation of :class:`CourseGenerationAI`."""

    def __init__(
        self,
        model: str,
        client: Optional[AIClient] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        response_parser: Optional[AIResponseParser] = None,
    ) -> None:
        self._model = model
        self._client = client if client is not None else DummyAIClient()
        self._prompt_builder = (
            prompt_builder if prompt_builder is not None else PromptBuilder()
        )
        self._response_parser = (
            response_parser
            if response_parser is not None
            else AIResponseParser()
        )

    @classmethod
    def from_config(
        cls,
        config: OpenAIConfig,
        client: Optional[AIClient] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        response_parser: Optional[AIResponseParser] = None,
    ) -> OpenAICourseGenerationAI:
        """Create a provider wired with :class:`OpenAIClient` from *config*."""
        resolved_client = (
            client if client is not None else OpenAIClient(config)
        )
        return cls(
            model=config.model,
            client=resolved_client,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
        )

    def generate_lessons(
        self,
        request: LessonGenerationRequest,
    ) -> LessonGenerationResult:
        """Generate or refine lessons via OpenAI."""
        prompt = self._prompt_builder.build_lesson_generation_prompt(request)
        response = self._client.generate(prompt)
        return self._response_parser.parse_lessons(response)
