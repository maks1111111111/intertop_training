"""Admin Knowledge Base document listing for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.repositories import knowledge_chunk_repository, knowledge_document_repository

_STATUS_LABELS = {
    KnowledgeDocumentStatus.DRAFT: "Черновик",
    KnowledgeDocumentStatus.ACTIVE: "Активен",
    KnowledgeDocumentStatus.ARCHIVED: "Архив",
}


class AdminKnowledgeError(Exception):
    """Raised when admin Knowledge Base data cannot be loaded safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminKnowledgeDocumentItem:
    """One Knowledge Base document row for the admin UI."""

    document_id: str
    title: str
    original_filename: str
    source_type: str
    source_language: str
    status: str
    status_label: str
    version: int
    created_at: str


@dataclass(frozen=True)
class AdminKnowledgeDocumentChunkView:
    """One persisted chunk for the admin document viewer."""

    chunk_index: int
    text: str
    anchor_id: str


@dataclass(frozen=True)
class AdminKnowledgeDocumentDetailView:
    """Detailed read-only view of one Knowledge Base document."""

    document_id: str
    title: str
    original_filename: str
    source_type: str
    source_language: str
    status: str
    status_label: str
    version: int
    created_at: str
    chunk_count: int
    chunks: tuple[AdminKnowledgeDocumentChunkView, ...]
    list_url: str
    focus_chunk_index: Optional[int] = None


def _status_label(status: KnowledgeDocumentStatus) -> str:
    return _STATUS_LABELS.get(status, status.value)


def _map_document(document: KnowledgeDocument) -> AdminKnowledgeDocumentItem:
    return AdminKnowledgeDocumentItem(
        document_id=document.document_id,
        title=document.title,
        original_filename=document.original_filename,
        source_type=document.source_type.value,
        source_language=document.source_language,
        status=document.status.value,
        status_label=_status_label(document.status),
        version=document.version,
        created_at=document.created_at,
    )


def _map_document_detail(
    document: KnowledgeDocument,
    *,
    chunks: tuple[AdminKnowledgeDocumentChunkView, ...],
    focus_chunk_index: Optional[int] = None,
) -> AdminKnowledgeDocumentDetailView:
    return AdminKnowledgeDocumentDetailView(
        document_id=document.document_id,
        title=document.title,
        original_filename=document.original_filename,
        source_type=document.source_type.value,
        source_language=document.source_language,
        status=document.status.value,
        status_label=_status_label(document.status),
        version=document.version,
        created_at=document.created_at,
        chunk_count=len(chunks),
        chunks=chunks,
        list_url="/admin/knowledge",
        focus_chunk_index=focus_chunk_index,
    )


class AdminKnowledgeService:
    """Read-only admin access to tenant-scoped Knowledge Base documents."""

    def __init__(
        self,
        db_path: Path,
        *,
        list_documents: Optional[
            Callable[..., list[KnowledgeDocument]]
        ] = None,
        get_document: Optional[
            Callable[..., Optional[KnowledgeDocument]]
        ] = None,
        list_chunks: Optional[Callable[..., list]] = None,
    ) -> None:
        self._db_path = db_path
        self._list_documents = (
            list_documents or knowledge_document_repository.list_for_company
        )
        self._get_document = (
            get_document or knowledge_document_repository.get_by_document_id
        )
        self._list_chunks = (
            list_chunks or knowledge_chunk_repository.list_for_document
        )

    def get_documents(self, company_id: str) -> tuple[AdminKnowledgeDocumentItem, ...]:
        """Return all Knowledge Base documents for one company."""
        normalized_company_id = self._normalize_company_id(company_id)

        documents = self._list_documents(
            self._db_path,
            company_id=normalized_company_id,
        )
        return tuple(_map_document(document) for document in documents)

    def get_document_detail(
        self,
        company_id: str,
        document_id: str,
        *,
        focus_chunk_index: Optional[int] = None,
    ) -> Optional[AdminKnowledgeDocumentDetailView]:
        """Return one tenant-scoped document detail view or None."""
        normalized_company_id = self._normalize_company_id(company_id)
        normalized_document_id = str(document_id or "").strip()
        if not normalized_document_id:
            return None

        document = self._get_document(
            self._db_path,
            company_id=normalized_company_id,
            document_id=normalized_document_id,
        )
        if document is None:
            return None

        chunk_rows = self._list_chunks(
            self._db_path,
            company_id=normalized_company_id,
            document_id=normalized_document_id,
        )
        chunks = tuple(
            AdminKnowledgeDocumentChunkView(
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                anchor_id=f"chunk-{chunk.chunk_index}",
            )
            for chunk in chunk_rows
        )
        normalized_focus = focus_chunk_index
        if normalized_focus is not None:
            known_indexes = {chunk.chunk_index for chunk in chunks}
            if normalized_focus not in known_indexes:
                normalized_focus = None

        return _map_document_detail(
            document,
            chunks=chunks,
            focus_chunk_index=normalized_focus,
        )

    @staticmethod
    def _normalize_company_id(company_id: str) -> str:
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise AdminKnowledgeError("Идентификатор компании обязателен.")
        return normalized_company_id
