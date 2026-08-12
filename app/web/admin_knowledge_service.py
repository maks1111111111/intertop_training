"""Admin Knowledge Base document listing for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.repositories import knowledge_document_repository

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


class AdminKnowledgeService:
    """Read-only admin access to tenant-scoped Knowledge Base documents."""

    def __init__(
        self,
        db_path: Path,
        *,
        list_documents: Optional[
            Callable[..., list[KnowledgeDocument]]
        ] = None,
    ) -> None:
        self._db_path = db_path
        self._list_documents = (
            list_documents or knowledge_document_repository.list_for_company
        )

    def get_documents(self, company_id: str) -> tuple[AdminKnowledgeDocumentItem, ...]:
        """Return all Knowledge Base documents for one company."""
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise AdminKnowledgeError("Идентификатор компании обязателен.")

        documents = self._list_documents(
            self._db_path,
            company_id=normalized_company_id,
        )
        return tuple(_map_document(document) for document in documents)
