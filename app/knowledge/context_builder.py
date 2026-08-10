"""Build bounded retrieval context for future Knowledge Base AI answering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.knowledge.models import KnowledgeDocumentChunk
from app.knowledge.retrieval import KnowledgeRetrievalResult

DEFAULT_MAX_SOURCES = 5
DEFAULT_MAX_TOTAL_CHARS = 8000
DEFAULT_SEPARATOR = "\n\n"


class KnowledgeContextBuildingError(Exception):
    """Raised when a context-building request is invalid."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class KnowledgeContextSource:
    """One source chunk included in a retrieval context."""

    company_id: str
    document_id: str
    chunk_index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class KnowledgeRetrievalContext:
    """Bounded, deterministic context derived from ranked retrieval results."""

    query: str
    sources: tuple[KnowledgeContextSource, ...]
    context_text: str
    source_count: int
    total_chars: int
    truncated: bool


@dataclass(frozen=True)
class KnowledgeContextBuildingOptions:
    """Limits and formatting for retrieval context assembly."""

    max_sources: int = DEFAULT_MAX_SOURCES
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS
    separator: str = DEFAULT_SEPARATOR


def _validate_non_empty(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise KnowledgeContextBuildingError(message)
    return normalized


def _validate_options(options: KnowledgeContextBuildingOptions) -> None:
    if options.max_sources <= 0:
        raise KnowledgeContextBuildingError("max_sources must be positive")
    if options.max_total_chars <= 0:
        raise KnowledgeContextBuildingError("max_total_chars must be positive")


def _source_from_chunk(chunk: KnowledgeDocumentChunk, text: str) -> KnowledgeContextSource:
    return KnowledgeContextSource(
        company_id=chunk.company_id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        text=text,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
    )


def _format_source_header(source_number: int, document_id: str, chunk_index: int) -> str:
    return (
        f"[Source {source_number} | document={document_id} | chunk={chunk_index}]\n"
    )


def _assert_tenant_match(
    expected_company_id: str,
    result: KnowledgeRetrievalResult,
) -> None:
    if result.chunk.company_id != expected_company_id:
        raise KnowledgeContextBuildingError(
            "Retrieval result does not belong to the requested company."
        )


class KnowledgeRetrievalContextBuilder:
    """Convert ranked retrieval results into a bounded AI-ready context."""

    def build(
        self,
        *,
        company_id: str,
        query: str,
        results: Sequence[KnowledgeRetrievalResult],
        options: Optional[KnowledgeContextBuildingOptions] = None,
    ) -> KnowledgeRetrievalContext:
        normalized_company_id = _validate_non_empty(
            company_id,
            "company_id must not be empty",
        )
        normalized_query = _validate_non_empty(
            query,
            "query must not be empty",
        )
        resolved_options = options or KnowledgeContextBuildingOptions()
        _validate_options(resolved_options)

        if not results:
            return KnowledgeRetrievalContext(
                query=normalized_query,
                sources=(),
                context_text="",
                source_count=0,
                total_chars=0,
                truncated=False,
            )

        selected = results[: resolved_options.max_sources]
        for result in selected:
            _assert_tenant_match(normalized_company_id, result)

        context_parts: list[str] = []
        sources: list[KnowledgeContextSource] = []
        truncated = False
        total_chars = 0

        for index, result in enumerate(selected, start=1):
            chunk = result.chunk
            header = _format_source_header(index, chunk.document_id, chunk.chunk_index)
            prefix = (
                resolved_options.separator + header
                if context_parts
                else header
            )
            chunk_text = chunk.text

            current_length = sum(len(part) for part in context_parts)
            remaining = resolved_options.max_total_chars - current_length

            if remaining <= len(prefix):
                break

            available_for_text = remaining - len(prefix)
            if len(chunk_text) <= available_for_text:
                included_text = chunk_text
            else:
                included_text = chunk_text[:available_for_text]
                if not included_text.strip():
                    break
                truncated = True

            block = prefix + included_text
            context_parts.append(block)
            sources.append(_source_from_chunk(chunk, included_text))
            total_chars += len(included_text)

            if truncated:
                break

        context_text = "".join(context_parts)

        return KnowledgeRetrievalContext(
            query=normalized_query,
            sources=tuple(sources),
            context_text=context_text,
            source_count=len(sources),
            total_chars=total_chars,
            truncated=truncated,
        )
