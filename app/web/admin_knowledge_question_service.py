"""Admin Knowledge Base question answering for the Web UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.ai.review_language import normalize_review_language
from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentChunk
from app.knowledge.question_answering_service import (
    KnowledgeQuestionAnsweringError,
    KnowledgeQuestionAnsweringService,
)
from app.repositories import knowledge_chunk_repository, knowledge_document_repository

_UNKNOWN_ERROR_MESSAGE = "Не удалось получить ответ по базе знаний."
_EXCERPT_MAX_LENGTH = 240
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?…])\s+")
_OCR_GARBAGE_PATTERN = re.compile(
    r"(?:Made\s*by|010203|\b[A-Z]{8,}\b|\d{5,})",
)


class AdminKnowledgeQuestionError(Exception):
    """Raised when a Knowledge Base question cannot be answered safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminKnowledgeAnswerSource:
    """One cited Knowledge Base source for the admin answer view."""

    source_number: int
    document_id: str
    chunk_index: int
    title: str
    original_filename: str


@dataclass(frozen=True)
class AdminKnowledgeAnswerChunkExcerpt:
    """One cited chunk excerpt shown in a grouped source card."""

    chunk_index: int
    excerpt: str


@dataclass(frozen=True)
class AdminKnowledgeAnswerSourceGroup:
    """Grouped cited sources for one Knowledge Base document."""

    document_id: str
    title: str
    original_filename: str
    view_url: str
    excerpts: tuple[AdminKnowledgeAnswerChunkExcerpt, ...]
    fragment_count: int


@dataclass(frozen=True)
class AdminKnowledgeAnswerView:
    """Web-friendly grounded Knowledge Base answer."""

    question: str
    answer: str
    sufficient_context: bool
    sources: tuple[AdminKnowledgeAnswerSource, ...]
    source_groups: tuple[AdminKnowledgeAnswerSourceGroup, ...]


class AdminKnowledgeQuestionService:
    """Web boundary for tenant-scoped grounded Knowledge Base Q&A."""

    def __init__(
        self,
        db_path: Path,
        *,
        question_answering_service: KnowledgeQuestionAnsweringService,
        get_document: Optional[
            Callable[..., Optional[KnowledgeDocument]]
        ] = None,
        list_chunks: Optional[
            Callable[..., list[KnowledgeDocumentChunk]]
        ] = None,
    ) -> None:
        self._db_path = db_path
        self._question_answering_service = question_answering_service
        self._get_document = (
            get_document or knowledge_document_repository.get_by_document_id
        )
        self._list_chunks = (
            list_chunks or knowledge_chunk_repository.list_for_document
        )

    def answer_question(
        self,
        company_id: str,
        question: str,
        language: str = "ru",
    ) -> AdminKnowledgeAnswerView:
        """Answer one tenant-scoped question using the grounded Q&A stack."""
        normalized_company_id = self._normalize_company_id(company_id)
        normalized_question = self._normalize_question(question)
        normalized_language = self._normalize_language(language)

        try:
            result = self._question_answering_service.answer(
                self._db_path,
                company_id=normalized_company_id,
                question=normalized_question,
                language=normalized_language,
            )
        except KnowledgeQuestionAnsweringError as exc:
            raise AdminKnowledgeQuestionError(_UNKNOWN_ERROR_MESSAGE) from exc
        except Exception as exc:
            raise AdminKnowledgeQuestionError(_UNKNOWN_ERROR_MESSAGE) from exc

        return self._map_result(
            normalized_question,
            result,
            company_id=normalized_company_id,
        )

    def _map_result(
        self,
        question: str,
        result: KnowledgeAnswerResult,
        *,
        company_id: str,
    ) -> AdminKnowledgeAnswerView:
        sources = tuple(
            self._enrich_citation(citation, company_id=company_id)
            for citation in result.citations
        )
        source_groups = self._build_source_groups(
            result.citations,
            company_id=company_id,
        )
        return AdminKnowledgeAnswerView(
            question=question,
            answer=result.answer,
            sufficient_context=result.sufficient_context,
            sources=sources,
            source_groups=source_groups,
        )

    def _build_source_groups(
        self,
        citations: tuple[KnowledgeAnswerCitation, ...],
        *,
        company_id: str,
    ) -> tuple[AdminKnowledgeAnswerSourceGroup, ...]:
        if not citations:
            return ()

        grouped: dict[str, list[int]] = {}
        order: list[str] = []
        for citation in citations:
            if citation.document_id not in grouped:
                grouped[citation.document_id] = []
                order.append(citation.document_id)
            if citation.chunk_index not in grouped[citation.document_id]:
                grouped[citation.document_id].append(citation.chunk_index)

        groups: list[AdminKnowledgeAnswerSourceGroup] = []
        for document_id in order:
            chunk_indexes = grouped[document_id]
            document = self._get_document(
                self._db_path,
                company_id=company_id,
                document_id=document_id,
            )
            title = document.title if document is not None else ""
            original_filename = (
                document.original_filename if document is not None else ""
            )
            chunk_texts = self._load_chunk_texts(
                company_id=company_id,
                document_id=document_id,
            )
            excerpts = tuple(
                AdminKnowledgeAnswerChunkExcerpt(
                    chunk_index=chunk_index,
                    excerpt=self._build_excerpt(
                        chunk_texts.get(chunk_index, "")
                    ),
                )
                for chunk_index in chunk_indexes
            )
            groups.append(
                AdminKnowledgeAnswerSourceGroup(
                    document_id=document_id,
                    title=title,
                    original_filename=original_filename,
                    view_url=self._build_view_url(document_id, chunk_indexes),
                    excerpts=excerpts,
                    fragment_count=len(chunk_indexes),
                )
            )
        return tuple(groups)

    @staticmethod
    def _build_view_url(document_id: str, chunk_indexes: list[int]) -> str:
        base = f"/admin/knowledge/{document_id}"
        if not chunk_indexes:
            return base
        if len(chunk_indexes) == 1:
            return f"{base}?chunk={chunk_indexes[0]}"
        return base

    def _load_chunk_texts(
        self,
        *,
        company_id: str,
        document_id: str,
    ) -> dict[int, str]:
        try:
            chunks = self._list_chunks(
                self._db_path,
                company_id=company_id,
                document_id=document_id,
            )
        except Exception:
            return {}
        return {chunk.chunk_index: chunk.text for chunk in chunks}

    @staticmethod
    def _build_excerpt(text: str) -> str:
        candidate = AdminKnowledgeQuestionService._select_meaningful_excerpt(text)
        if not candidate:
            return ""
        normalized = " ".join(candidate.split())
        if len(normalized) <= _EXCERPT_MAX_LENGTH:
            return normalized
        return normalized[: _EXCERPT_MAX_LENGTH - 1].rstrip() + "…"

    @staticmethod
    def _select_meaningful_excerpt(text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""

        candidates: list[str] = []
        for paragraph in normalized.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            parts = _SENTENCE_SPLIT_PATTERN.split(paragraph)
            if not parts:
                parts = [paragraph]
            for part in parts:
                cleaned = " ".join(part.split())
                if cleaned:
                    candidates.append(cleaned)

        if not candidates:
            candidates = [" ".join(normalized.split())]

        for candidate in candidates:
            if AdminKnowledgeQuestionService._is_meaningful_excerpt(candidate):
                return candidate

        fallback = candidates[-1]
        if AdminKnowledgeQuestionService._is_meaningful_excerpt(fallback):
            return fallback
        return ""

    @staticmethod
    def _is_meaningful_excerpt(text: str) -> bool:
        cleaned = " ".join(str(text or "").split())
        if len(cleaned) < 20:
            return False
        if _OCR_GARBAGE_PATTERN.search(cleaned):
            return False

        letters = sum(character.isalpha() for character in cleaned)
        digits = sum(character.isdigit() for character in cleaned)
        if letters == 0:
            return False
        if digits > 0 and digits >= letters:
            return False

        uppercase_letters = sum(
            1 for character in cleaned if character.isalpha() and character.isupper()
        )
        if letters >= 12 and uppercase_letters / letters > 0.85:
            if " " not in cleaned:
                return False

        return True

    def _enrich_citation(
        self,
        citation: KnowledgeAnswerCitation,
        *,
        company_id: str,
    ) -> AdminKnowledgeAnswerSource:
        document = self._get_document(
            self._db_path,
            company_id=company_id,
            document_id=citation.document_id,
        )
        if document is None:
            return AdminKnowledgeAnswerSource(
                source_number=citation.source_number,
                document_id=citation.document_id,
                chunk_index=citation.chunk_index,
                title="",
                original_filename="",
            )
        return AdminKnowledgeAnswerSource(
            source_number=citation.source_number,
            document_id=citation.document_id,
            chunk_index=citation.chunk_index,
            title=document.title,
            original_filename=document.original_filename,
        )

    def _normalize_company_id(self, company_id: str) -> str:
        normalized = str(company_id or "").strip()
        if not normalized:
            raise AdminKnowledgeQuestionError("Идентификатор компании обязателен.")
        return normalized

    def _normalize_question(self, question: str) -> str:
        normalized = str(question or "").strip()
        if not normalized:
            raise AdminKnowledgeQuestionError("Вопрос обязателен.")
        return normalized

    def _normalize_language(self, language: str) -> str:
        normalized = normalize_review_language(str(language or ""))
        if normalized is None:
            raise AdminKnowledgeQuestionError("Неподдерживаемый язык ответа.")
        return normalized
