"""AI service layer for grounded Knowledge Base answering.

Orchestrates prompt building, AI text generation, response parsing, and
semantic validation into a single entry point for knowledge-base Q&A.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient
from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_prompt_builder import (
    KnowledgeAnswerPromptBuilder,
    KnowledgeAnswerPromptBuildingError,
)
from app.ai.knowledge_answer_response_parser import (
    KnowledgeAnswerResponseParser,
    KnowledgeAnswerResponseParsingError,
)
from app.ai.knowledge_answer_validator import (
    KnowledgeAnswerValidator,
    KnowledgeAnswerValidationError,
)


class KnowledgeAnswerGenerationError(Exception):
    """Raised when grounded Knowledge Base answer generation fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class KnowledgeAnswerService:
    """Application service for grounded Knowledge Base AI answering."""

    def __init__(
        self,
        provider: AIClient,
        prompt_builder: Optional[KnowledgeAnswerPromptBuilder] = None,
        response_parser: Optional[KnowledgeAnswerResponseParser] = None,
        validator: Optional[KnowledgeAnswerValidator] = None,
    ) -> None:
        """Initialize the service with injectable pipeline dependencies.

        Args:
            provider: AI client used to execute the built prompt.
            prompt_builder: Optional prompt builder; defaults to
                :class:`KnowledgeAnswerPromptBuilder`.
            response_parser: Optional response parser; defaults to
                :class:`KnowledgeAnswerResponseParser`.
            validator: Optional semantic validator; defaults to
                :class:`KnowledgeAnswerValidator`.
        """
        self._provider = provider
        self._prompt_builder = (
            prompt_builder
            if prompt_builder is not None
            else KnowledgeAnswerPromptBuilder()
        )
        self._response_parser = (
            response_parser
            if response_parser is not None
            else KnowledgeAnswerResponseParser()
        )
        self._validator = (
            validator if validator is not None else KnowledgeAnswerValidator()
        )

    def answer(
        self,
        request: KnowledgeAnswerRequest,
    ) -> KnowledgeAnswerResult:
        """Generate a grounded answer via prompt, AI, parsing, and validation.

        Args:
            request: Grounded answer request with question and retrieval context.

        Returns:
            Validated :class:`KnowledgeAnswerResult`.

        Raises:
            KnowledgeAnswerGenerationError: If prompt building, provider
                execution, parsing, or validation fails.
        """
        try:
            prompt = self._prompt_builder.build(request)
        except KnowledgeAnswerPromptBuildingError as exc:
            raise KnowledgeAnswerGenerationError(exc.message) from exc

        try:
            raw_response = self._provider.generate(prompt)
        except KnowledgeAnswerGenerationError:
            raise
        except Exception as exc:
            raise KnowledgeAnswerGenerationError(
                "Failed to generate knowledge answer."
            ) from exc

        try:
            parsed = self._response_parser.parse(raw_response)
        except KnowledgeAnswerResponseParsingError as exc:
            raise KnowledgeAnswerGenerationError(exc.message) from exc

        try:
            return self._validator.validate(parsed, request.context)
        except KnowledgeAnswerValidationError as exc:
            raise KnowledgeAnswerGenerationError(exc.message) from exc
