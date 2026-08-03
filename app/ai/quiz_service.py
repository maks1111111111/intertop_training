"""AI service layer for quiz generation.

Orchestrates prompt building, AI text generation, and response parsing
into a single entry point for quiz generation workflows.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient
from app.ai.quiz_interfaces import QuizGenerationRequest, QuizGenerationResult
from app.ai.quiz_prompt_builder import QuizPromptBuilder
from app.ai.quiz_response_parser import QuizResponseParser


class QuizGenerationService:
    """Application service that generates quizzes via prompt, AI, and parsing."""

    def __init__(
        self,
        provider: AIClient,
        prompt_builder: Optional[QuizPromptBuilder] = None,
        response_parser: Optional[QuizResponseParser] = None,
    ) -> None:
        self._provider = provider
        self._prompt_builder = (
            prompt_builder if prompt_builder is not None else QuizPromptBuilder()
        )
        self._response_parser = (
            response_parser if response_parser is not None else QuizResponseParser()
        )

    def generate_quiz(
        self,
        request: QuizGenerationRequest,
    ) -> QuizGenerationResult:
        """Build a prompt, call the AI provider, and parse the response."""
        prompt = self._prompt_builder.build_quiz_generation_prompt(request)
        if prompt == "":
            raise ValueError("Quiz generation prompt must not be empty.")
        response = self._provider.generate(prompt)
        return self._response_parser.parse_quiz(response)
