"""Admin Knowledge Base question answering for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.ai.review_language import normalize_review_language
from app.knowledge.models import KnowledgeDocument
from app.knowledge.question_answering_service import (
    KnowledgeQuestionAnsweringError,
    KnowledgeQuestionAnsweringService,
)
from app.repositories import knowledge_document_repository

_UNKNOWN_ERROR_MESSAGE = "Не удалось получить ответ по базе знаний."


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
class AdminKnowledgeAnswerView:
    """Web-friendly grounded Knowledge Base answer."""

    question: str
    answer: str
    sufficient_context: bool
    sources: tuple[AdminKnowledgeAnswerSource, ...]


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
    ) -> None:
        self._db_path = db_path
        self._question_answering_service = question_answering_service
        self._get_document = (
            get_document or knowledge_document_repository.get_by_document_id
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
        return AdminKnowledgeAnswerView(
            question=question,
            answer=result.answer,
            sufficient_context=result.sufficient_context,
            sources=sources,
        )

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
