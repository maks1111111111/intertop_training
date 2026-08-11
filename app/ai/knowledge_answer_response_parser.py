"""Parse AI model responses into grounded Knowledge Base answer results."""

from __future__ import annotations

import json
from typing import Any, Tuple

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)


class KnowledgeAnswerResponseParsingError(Exception):
    """Raised when a knowledge-answer AI response cannot be parsed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class KnowledgeAnswerResponseParser:
    """Convert raw AI JSON text into :class:`KnowledgeAnswerResult`."""

    def parse(self, raw_response: str) -> KnowledgeAnswerResult:
        """Parse model output into a grounded answer result.

        Args:
            raw_response: Raw JSON text from the AI model.

        Returns:
            Parsed :class:`KnowledgeAnswerResult`.

        Raises:
            KnowledgeAnswerResponseParsingError: If the response is empty,
                malformed, or structurally invalid.
        """
        if raw_response is None or not raw_response.strip():
            raise KnowledgeAnswerResponseParsingError(
                "Response must not be empty."
            )

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise KnowledgeAnswerResponseParsingError(
                "Response must be valid JSON."
            ) from exc

        if not isinstance(data, dict):
            raise KnowledgeAnswerResponseParsingError(
                "Response root must be a JSON object."
            )

        answer = _parse_answer(data)
        sufficient_context = _parse_sufficient_context(data)
        citations = _parse_citations(data)

        return KnowledgeAnswerResult(
            answer=answer,
            citations=citations,
            sufficient_context=sufficient_context,
        )


def _parse_answer(data: dict[str, Any]) -> str:
    if "answer" not in data:
        raise KnowledgeAnswerResponseParsingError("Field 'answer' is required.")

    answer = data["answer"]
    if not isinstance(answer, str):
        raise KnowledgeAnswerResponseParsingError(
            "Field 'answer' must be a string."
        )

    normalized = answer.strip()
    if not normalized:
        raise KnowledgeAnswerResponseParsingError(
            "Field 'answer' must not be empty."
        )

    return normalized


def _parse_sufficient_context(data: dict[str, Any]) -> bool:
    if "sufficient_context" not in data:
        raise KnowledgeAnswerResponseParsingError(
            "Field 'sufficient_context' is required."
        )

    sufficient_context = data["sufficient_context"]
    if not isinstance(sufficient_context, bool):
        raise KnowledgeAnswerResponseParsingError(
            "Field 'sufficient_context' must be a boolean."
        )

    return sufficient_context


def _parse_citations(data: dict[str, Any]) -> Tuple[KnowledgeAnswerCitation, ...]:
    if "citations" not in data:
        raise KnowledgeAnswerResponseParsingError(
            "Field 'citations' is required."
        )

    raw_citations = data["citations"]
    if not isinstance(raw_citations, list):
        raise KnowledgeAnswerResponseParsingError(
            "Field 'citations' must be a list."
        )

    citations: list[KnowledgeAnswerCitation] = []
    for index, item in enumerate(raw_citations):
        citations.append(_parse_citation_item(item, index))

    return tuple(citations)


def _parse_citation_item(item: Any, index: int) -> KnowledgeAnswerCitation:
    if not isinstance(item, dict):
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} must be a JSON object."
        )

    source_number = _parse_citation_source_number(item, index)
    document_id = _parse_citation_document_id(item, index)
    chunk_index = _parse_citation_chunk_index(item, index)

    return KnowledgeAnswerCitation(
        source_number=source_number,
        document_id=document_id,
        chunk_index=chunk_index,
    )


def _parse_citation_source_number(item: dict[str, Any], index: int) -> int:
    if "source_number" not in item:
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} is missing 'source_number'."
        )

    source_number = item["source_number"]
    if isinstance(source_number, bool) or not isinstance(source_number, int):
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} field 'source_number' must be an integer."
        )

    if source_number < 1:
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} field 'source_number' must be >= 1."
        )

    return source_number


def _parse_citation_document_id(item: dict[str, Any], index: int) -> str:
    if "document_id" not in item:
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} is missing 'document_id'."
        )

    document_id = item["document_id"]
    if not isinstance(document_id, str):
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} field 'document_id' must be a string."
        )

    normalized = document_id.strip()
    if not normalized:
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} field 'document_id' must not be empty."
        )

    return normalized


def _parse_citation_chunk_index(item: dict[str, Any], index: int) -> int:
    if "chunk_index" not in item:
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} is missing 'chunk_index'."
        )

    chunk_index = item["chunk_index"]
    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} field 'chunk_index' must be an integer."
        )

    if chunk_index < 0:
        raise KnowledgeAnswerResponseParsingError(
            f"Citation at index {index} field 'chunk_index' must be >= 0."
        )

    return chunk_index
