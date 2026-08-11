"""AI knowledge-base answer data contracts.

Defines request/result models for grounded corporate Knowledge Base answering.
No concrete AI providers or business logic are included here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple

from app.knowledge.context_builder import KnowledgeRetrievalContext


@dataclass(frozen=True)
class KnowledgeAnswerCitation:
    """Reference to a source chunk supporting an answer."""

    source_number: int
    document_id: str
    chunk_index: int


@dataclass(frozen=True)
class KnowledgeAnswerRequest:
    """Input for grounded Knowledge Base AI answering."""

    question: str
    context: KnowledgeRetrievalContext
    language: str = "ru"


@dataclass(frozen=True)
class KnowledgeAnswerResult:
    """Outcome of grounded Knowledge Base AI answering."""

    answer: str
    citations: Tuple[KnowledgeAnswerCitation, ...]
    sufficient_context: bool


class KnowledgeAnswerAI(Protocol):
    """Protocol for AI backends that answer from Knowledge Base context."""

    def answer(
        self,
        request: KnowledgeAnswerRequest,
    ) -> KnowledgeAnswerResult:
        """Answer a question using the supplied retrieval context."""
        ...
