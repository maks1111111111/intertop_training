"""AI service layer for practical-task generation."""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient
from app.ai.practical_task_generation_interfaces import (
    PracticalTaskGenerationRequest,
    PracticalTaskGenerationResult,
)
from app.ai.practical_task_prompt_builder import PracticalTaskPromptBuilder
from app.ai.practical_task_response_parser import PracticalTaskResponseParser


class PracticalTaskGenerationService:
    """Application service that generates practical tasks via prompt, AI, and parsing."""

    def __init__(
        self,
        provider: AIClient,
        prompt_builder: Optional[PracticalTaskPromptBuilder] = None,
        response_parser: Optional[PracticalTaskResponseParser] = None,
    ) -> None:
        self._provider = provider
        self._prompt_builder = (
            prompt_builder
            if prompt_builder is not None
            else PracticalTaskPromptBuilder()
        )
        self._response_parser = (
            response_parser
            if response_parser is not None
            else PracticalTaskResponseParser()
        )

    def generate_practical_task(
        self,
        request: PracticalTaskGenerationRequest,
    ) -> PracticalTaskGenerationResult:
        """Build a prompt, call the AI provider, and parse the response."""
        prompt = self._prompt_builder.build_practical_task_generation_prompt(request)
        if prompt == "":
            raise ValueError("Practical task generation prompt must not be empty.")
        response = self._provider.generate(prompt)
        return self._response_parser.parse_practical_task(response)
