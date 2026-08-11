"""Lexical retrieval for Knowledge Base document chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.knowledge.models import KnowledgeDocumentChunk, KnowledgeDocumentStatus
from app.repositories import knowledge_chunk_repository

_TOKEN_SPLIT_RE = re.compile(r"[^\w]+", flags=re.UNICODE)

ChunkLoader = Callable[[Path, str], Sequence[KnowledgeDocumentChunk]]


class KnowledgeRetrievalError(Exception):
    """Raised when a knowledge retrieval request is invalid."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    """One ranked chunk returned by lexical search."""

    chunk: KnowledgeDocumentChunk
    score: float


def _validate_non_empty(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise KnowledgeRetrievalError(message)
    return normalized


def tokenize(text: str) -> tuple[str, ...]:
    """Split text into lowercase Unicode word tokens."""
    normalized = text.casefold()
    parts = _TOKEN_SPLIT_RE.split(normalized)
    return tuple(part for part in parts if part)


def unique_query_terms(query: str) -> tuple[str, ...]:
    """Return unique query tokens in first-seen order."""
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokenize(query):
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return tuple(unique)


def score_chunk(query_terms: Sequence[str], chunk_text: str) -> float:
    """Score one chunk by unique query-term coverage (0.0 when no overlap)."""
    if not query_terms:
        return 0.0

    chunk_term_set = set(tokenize(chunk_text))
    if not chunk_term_set:
        return 0.0

    matched = sum(1 for term in query_terms if term in chunk_term_set)
    if matched == 0:
        return 0.0

    coverage = matched / len(query_terms)

    normalized_query = " ".join(query_terms)
    normalized_chunk = " ".join(tokenize(chunk_text))
    phrase_bonus = 0.0
    if len(query_terms) > 1 and normalized_query in normalized_chunk:
        phrase_bonus = 0.1

    return min(1.0, coverage + phrase_bonus)


def rank_chunks(
    query: str,
    chunks: Sequence[KnowledgeDocumentChunk],
) -> tuple[KnowledgeRetrievalResult, ...]:
    """Rank chunks deterministically by lexical relevance."""
    query_terms = unique_query_terms(query)
    if not query_terms:
        return ()

    scored: list[KnowledgeRetrievalResult] = []
    for chunk in chunks:
        score = score_chunk(query_terms, chunk.text)
        if score <= 0.0:
            continue
        scored.append(KnowledgeRetrievalResult(chunk=chunk, score=score))

    scored.sort(
        key=lambda result: (
            -result.score,
            result.chunk.document_id,
            result.chunk.chunk_index,
            result.chunk.id,
        )
    )
    return tuple(scored)


def _default_chunk_loader(
    db_path: Path,
    company_id: str,
) -> Sequence[KnowledgeDocumentChunk]:
    return knowledge_chunk_repository.list_for_company_by_document_status(
        db_path,
        company_id=company_id,
        status=KnowledgeDocumentStatus.ACTIVE,
    )


class KnowledgeChunkRetrievalService:
    """Deterministic lexical search over tenant-scoped knowledge chunks."""

    def __init__(
        self,
        chunk_loader: Optional[ChunkLoader] = None,
    ) -> None:
        if chunk_loader is None:
            self._chunk_loader = _default_chunk_loader
        else:
            self._chunk_loader = chunk_loader

    def search(
        self,
        db_path: Path,
        *,
        company_id: str,
        query: str,
        limit: int = 5,
    ) -> tuple[KnowledgeRetrievalResult, ...]:
        normalized_company_id = _validate_non_empty(
            company_id,
            "company_id must not be empty",
        )
        normalized_query = _validate_non_empty(
            query,
            "query must not be empty",
        )
        if limit <= 0:
            raise KnowledgeRetrievalError("limit must be positive")

        chunks = self._chunk_loader(db_path, company_id=normalized_company_id)
        ranked = rank_chunks(normalized_query, chunks)
        return ranked[:limit]
