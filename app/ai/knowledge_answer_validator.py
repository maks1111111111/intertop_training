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
            A validated result with canonicalized citations when needed.

        Raises:
            KnowledgeAnswerValidationError: If the answer is inconsistent with
                the supplied context or citation rules.
        """
        self._validate_context(context)
        self._validate_answer(result)
        self._validate_sufficient_context_rules(result, context)
        canonical_citations = self._canonicalize_citations(
            result.citations,
            context,
        )
        if canonical_citations is result.citations:
            return result
        return KnowledgeAnswerResult(
            answer=result.answer,
            citations=canonical_citations,
            sufficient_context=result.sufficient_context,
        )

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

    def _canonicalize_citations(
        self,
        citations: tuple[KnowledgeAnswerCitation, ...],
        context: KnowledgeRetrievalContext,
    ) -> tuple[KnowledgeAnswerCitation, ...]:
        seen_identities: set[tuple[str, int]] = set()
        canonical: list[KnowledgeAnswerCitation] = []

        for citation in citations:
            matches = [
                (index, source)
                for index, source in enumerate(context.sources)
                if source.document_id == citation.document_id
                and source.chunk_index == citation.chunk_index
            ]

            if not matches:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citation does not match the referenced "
                    "source."
                )

            if len(matches) > 1:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer citation does not match the referenced "
                    "source."
                )

            source_index, source = matches[0]
            identity = (source.document_id, source.chunk_index)
            if identity in seen_identities:
                raise KnowledgeAnswerValidationError(
                    "Knowledge answer contains duplicate citations."
                )
            seen_identities.add(identity)

            canonical.append(
                KnowledgeAnswerCitation(
                    source_number=source_index + 1,
                    document_id=source.document_id,
                    chunk_index=source.chunk_index,
                )
            )

        if canonical == list(citations):
            return citations
        return tuple(canonical)
