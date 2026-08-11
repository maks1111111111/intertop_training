"""Validate grounded Knowledge Base AI answers against retrieval context."""

from __future__ import annotations

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.knowledge.context_builder import KnowledgeRetrievalContext


class KnowledgeAnswerValidationError(Exception):
    """Raised when a knowledge answer fails semantic validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class KnowledgeAnswerValidator:
    """Validate :class:`KnowledgeAnswerResult` against retrieval context."""

    def validate(
        self,
        result: KnowledgeAnswerResult,
        context: KnowledgeRetrievalContext,
    ) -> KnowledgeAnswerResult:
        """Validate answer provenance and sufficient-context consistency.

        Args:
            result: Parsed AI answer to validate.
            context: Tenant-scoped retrieval context used for answering.

        Returns:
            The same ``result`` when validation succeeds.

        Raises:
            KnowledgeAnswerValidationError: If the answer is inconsistent with
                the supplied context or citation rules.
        """
        self._validate_context(context)
        self._validate_answer(result)
        self._validate_sufficient_context_rules(result, context)
        self._validate_citations(result.citations, context)
        return result

    def _validate_context(self, context: KnowledgeRetrievalContext) -> None:
        source_count = len(context.sources)
        if context.source_count != source_count:
            raise KnowledgeAnswerValidationError(
                "Knowledge answer context is inconsistent."
            )

        if source_count == 0 and context.context_text.strip():
            raise KnowledgeAnswerValidationError(
                "Knowledge answer context is inconsistent."
            )

    def _validate_answer(self, result: KnowledgeAnswerResult) -> None:
        if not result.answer.strip():
            raise KnowledgeAnswerValidationError(
                "Knowledge answer must not be empty."
            )

    def _validate_sufficient_context_rules(
        self,
        result: KnowledgeAnswerResult,
        context: KnowledgeRetrievalContext,
    ) -> None:
        source_count = len(context.sources)

        if source_count == 0:
            if result.sufficient_context:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer cannot have sufficient_context=true "
                    "with empty context."
                )
            if result.citations:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citations must be empty when context "
                    "has no sources."
                )
            return

        if result.sufficient_context and not result.citations:
            raise KnowledgeAnswerValidationError(
                "Knowledge answer requires at least one valid citation."
            )

    def _validate_citations(
        self,
        citations: tuple[KnowledgeAnswerCitation, ...],
        context: KnowledgeRetrievalContext,
    ) -> None:
        seen: set[tuple[int, str, int]] = set()
        source_count = len(context.sources)

        for citation in citations:
            identity = (
                citation.source_number,
                citation.document_id,
                citation.chunk_index,
            )
            if identity in seen:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer contains duplicate citations."
                )
            seen.add(identity)

            if citation.source_number < 1:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citation source_number is out of range."
                )

            if citation.source_number > source_count:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citation source_number is out of range."
                )

            source = context.sources[citation.source_number - 1]

            if citation.document_id != source.document_id:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citation does not match the referenced "
                    "source."
                )

            if citation.chunk_index != source.chunk_index:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citation does not match the referenced "
                    "source."
                )

