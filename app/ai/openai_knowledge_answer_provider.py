"""OpenAI wiring for grounded Knowledge Base answering.

Provides a factory for :class:`KnowledgeAnswerService` backed by
:class:`OpenAIClient`, and a thin :class:`OpenAIKnowledgeAnswerAI` adapter
that implements :class:`KnowledgeAnswerAI` without duplicating the
prompt/parse/validate pipeline owned by :class:`KnowledgeAnswerService`.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient
from app.ai.config import OpenAIConfig
from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_prompt_builder import KnowledgeAnswerPromptBuilder
from app.ai.knowledge_answer_response_parser import KnowledgeAnswerResponseParser
from app.ai.knowledge_answer_service import KnowledgeAnswerService
from app.ai.knowledge_answer_validator import KnowledgeAnswerValidator
from app.ai.openai_client import OpenAIClient


def create_knowledge_answer_service_from_config(
    config: OpenAIConfig,
    client: Optional[AIClient] = None,
    prompt_builder: Optional[KnowledgeAnswerPromptBuilder] = None,
    response_parser: Optional[KnowledgeAnswerResponseParser] = None,
    validator: Optional[KnowledgeAnswerValidator] = None,
) -> KnowledgeAnswerService:
    """Create a :class:`KnowledgeAnswerService` wired with OpenAI.

    Args:
        config: OpenAI configuration.
        client: Optional AI client; when omitted, constructs
            :class:`OpenAIClient` from *config*.
        prompt_builder: Optional prompt builder override.
        response_parser: Optional response parser override.
        validator: Optional validator override.

    Returns:
        Configured :class:`KnowledgeAnswerService` instance.
    """
    resolved_client = client if client is not None else OpenAIClient(config)
    return KnowledgeAnswerService(
        provider=resolved_client,
        prompt_builder=prompt_builder,
        response_parser=response_parser,
        validator=validator,
    )


class OpenAIKnowledgeAnswerAI:
    """Thin OpenAI adapter implementing :class:`KnowledgeAnswerAI`.

    Delegates all grounded answering workflow to
    :class:`KnowledgeAnswerService`.
    """

    def __init__(
        self,
        service: KnowledgeAnswerService,
        model: str,
    ) -> None:
        """Initialize the adapter with an existing answer service.

        Args:
            service: Application service that owns the answer pipeline.
            model: OpenAI model identifier associated with this wiring.
        """
        self._service = service
        self._model = model

    @property
    def service(self) -> KnowledgeAnswerService:
        """Return the underlying :class:`KnowledgeAnswerService`."""
        return self._service

    @classmethod
    def from_config(
        cls,
        config: OpenAIConfig,
        client: Optional[AIClient] = None,
        prompt_builder: Optional[KnowledgeAnswerPromptBuilder] = None,
        response_parser: Optional[KnowledgeAnswerResponseParser] = None,
        validator: Optional[KnowledgeAnswerValidator] = None,
    ) -> OpenAIKnowledgeAnswerAI:
        """Create an adapter wired with :class:`OpenAIClient` from *config*.

        Args:
            config: OpenAI configuration.
            client: Optional AI client; when omitted, constructs
                :class:`OpenAIClient` from *config*.
            prompt_builder: Optional prompt builder override.
            response_parser: Optional response parser override.
            validator: Optional validator override.

        Returns:
            Configured :class:`OpenAIKnowledgeAnswerAI` instance.
        """
        service = create_knowledge_answer_service_from_config(
            config,
            client=client,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            validator=validator,
        )
        return cls(service=service, model=config.model)

    def answer(
        self,
        request: KnowledgeAnswerRequest,
    ) -> KnowledgeAnswerResult:
        """Answer a question via the configured :class:`KnowledgeAnswerService`.

        Args:
            request: Grounded answer request with question and context.

        Returns:
            Validated :class:`KnowledgeAnswerResult`.

        Raises:
            KnowledgeAnswerGenerationError: If the answer pipeline fails.
        """
        return self._service.answer(request)
