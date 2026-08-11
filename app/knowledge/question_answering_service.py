"""Application service orchestrating knowledge retrieval and grounded AI answering."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_service import (
    KnowledgeAnswerGenerationError,
    KnowledgeAnswerService,
)
from app.knowledge.context_builder import (
    KnowledgeContextBuildingError,
    KnowledgeContextBuildingOptions,
)
from app.knowledge.context_service import KnowledgeRetrievalContextService
from app.knowledge.retrieval import KnowledgeRetrievalError


class KnowledgeQuestionAnsweringError(Exception):
    """Raised when tenant-scoped knowledge question answering fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class KnowledgeQuestionAnsweringService:
    """Orchestrate retrieval context building and grounded AI answering."""

    def __init__(
        self,
        context_service: KnowledgeRetrievalContextService,
        answer_service: KnowledgeAnswerService,
    ) -> None:
        self._context_service = context_service
        self._answer_service = answer_service

    def answer(
        self,
        db_path: Path,
        *,
        company_id: str,
        question: str,
        language: str = "ru",
        retrieval_limit: Optional[int] = None,
        context_options: Optional[KnowledgeContextBuildingOptions] = None,
    ) -> KnowledgeAnswerResult:
        """Build retrieval context and generate a grounded answer.

        Args:
            db_path: Database path for tenant-scoped retrieval.
            company_id: Tenant identifier.
            question: User question to answer.
            language: Response language code (ru, kk, en).
            retrieval_limit: Optional override for retrieval result count.
            context_options: Optional bounded context assembly options.

        Returns:
            Validated grounded answer result.

        Raises:
            KnowledgeQuestionAnsweringError: If context building or answer
                generation fails.
        """
        try:
            context = self._context_service.build_context(
                db_path,
                company_id=company_id,
                query=question,
                retrieval_limit=retrieval_limit,
                options=context_options,
            )
        except (KnowledgeRetrievalError, KnowledgeContextBuildingError) as exc:
            raise KnowledgeQuestionAnsweringError(
                "Failed to build knowledge answer context."
            ) from exc

        request = KnowledgeAnswerRequest(
            question=question,
            context=context,
            language=language,
        )

        try:
            return self._answer_service.answer(request)
        except KnowledgeAnswerGenerationError as exc:
            raise KnowledgeQuestionAnsweringError(
                "Failed to generate grounded knowledge answer."
            ) from exc
