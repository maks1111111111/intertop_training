"""Bootstrap factory for grounded Knowledge Base question answering.

Composes existing retrieval, context-building, and answer-generation services
into a single application entry point suitable for CLI and manual E2E testing.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient
from app.ai.config import OpenAIConfig
from app.ai.knowledge_answer_prompt_builder import KnowledgeAnswerPromptBuilder
from app.ai.knowledge_answer_response_parser import KnowledgeAnswerResponseParser
from app.ai.knowledge_answer_service import KnowledgeAnswerService
from app.ai.knowledge_answer_validator import KnowledgeAnswerValidator
from app.ai.openai_knowledge_answer_provider import (
    create_knowledge_answer_service_from_config,
)
from app.knowledge.context_service import KnowledgeRetrievalContextService
from app.knowledge.question_answering_service import KnowledgeQuestionAnsweringService


def create_knowledge_question_answering_service(
    config: OpenAIConfig,
    *,
    client: Optional[AIClient] = None,
    context_service: Optional[KnowledgeRetrievalContextService] = None,
    answer_service: Optional[KnowledgeAnswerService] = None,
    prompt_builder: Optional[KnowledgeAnswerPromptBuilder] = None,
    response_parser: Optional[KnowledgeAnswerResponseParser] = None,
    validator: Optional[KnowledgeAnswerValidator] = None,
) -> KnowledgeQuestionAnsweringService:
    """Create a :class:`KnowledgeQuestionAnsweringService` wired with OpenAI.

    Args:
        config: OpenAI configuration for the answer-generation pipeline.
        client: Optional AI client override for tests or custom wiring.
        context_service: Optional retrieval/context service override.
        answer_service: Optional answer service override; when omitted, builds
            one via :func:`create_knowledge_answer_service_from_config`.
        prompt_builder: Optional prompt builder passed to the answer service.
        response_parser: Optional response parser passed to the answer service.
        validator: Optional validator passed to the answer service.

    Returns:
        Configured :class:`KnowledgeQuestionAnsweringService` instance.
    """
    resolved_context_service = (
        context_service
        if context_service is not None
        else KnowledgeRetrievalContextService()
    )
    resolved_answer_service = (
        answer_service
        if answer_service is not None
        else create_knowledge_answer_service_from_config(
            config,
            client=client,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            validator=validator,
        )
    )
    return KnowledgeQuestionAnsweringService(
        context_service=resolved_context_service,
        answer_service=resolved_answer_service,
    )
