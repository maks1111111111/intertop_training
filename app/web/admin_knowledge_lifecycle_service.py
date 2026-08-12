"""Admin Knowledge Base document lifecycle actions for the Web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.knowledge.lifecycle_service import (
    KnowledgeDocumentLifecycleError,
    KnowledgeDocumentLifecycleService,
)
from app.knowledge.models import KnowledgeDocument

_LIFECYCLE_ERROR_MESSAGES = {
    "Knowledge document not found.": "Документ не найден.",
    "Archived knowledge documents cannot be published.": (
        "Архивные документы нельзя опубликовать."
    ),
    "Failed to update knowledge document status.": (
        "Не удалось изменить статус документа."
    ),
}

_UNKNOWN_LIFECYCLE_ERROR_MESSAGE = "Не удалось изменить статус документа."


def _map_lifecycle_error_message(message: str) -> str:
    """Map a lower-layer lifecycle error to a safe Web-facing Russian message."""
    return _LIFECYCLE_ERROR_MESSAGES.get(message, _UNKNOWN_LIFECYCLE_ERROR_MESSAGE)


class AdminKnowledgeLifecycleError(Exception):
    """Raised when a Knowledge Base lifecycle action cannot be completed safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AdminKnowledgeLifecycleService:
    """Web boundary for tenant-scoped Knowledge Base publish/archive actions."""

    def __init__(
        self,
        db_path: Path,
        *,
        lifecycle_service: Optional[KnowledgeDocumentLifecycleService] = None,
    ) -> None:
        self._db_path = db_path
        self._lifecycle_service = (
            lifecycle_service or KnowledgeDocumentLifecycleService()
        )

    def publish(
        self,
        company_id: str,
        document_id: str,
    ) -> KnowledgeDocument:
        """Publish one Knowledge Base document for the given company."""
        normalized_company_id = self._normalize_company_id(company_id)
        normalized_document_id = self._normalize_document_id(document_id)
        try:
            return self._lifecycle_service.publish(
                self._db_path,
                company_id=normalized_company_id,
                document_id=normalized_document_id,
            )
        except KnowledgeDocumentLifecycleError as exc:
            raise AdminKnowledgeLifecycleError(
                _map_lifecycle_error_message(exc.message)
            ) from exc

    def archive(
        self,
        company_id: str,
        document_id: str,
    ) -> KnowledgeDocument:
        """Archive one Knowledge Base document for the given company."""
        normalized_company_id = self._normalize_company_id(company_id)
        normalized_document_id = self._normalize_document_id(document_id)
        try:
            return self._lifecycle_service.archive(
                self._db_path,
                company_id=normalized_company_id,
                document_id=normalized_document_id,
            )
        except KnowledgeDocumentLifecycleError as exc:
            raise AdminKnowledgeLifecycleError(
                _map_lifecycle_error_message(exc.message)
            ) from exc

    def _normalize_company_id(self, company_id: str) -> str:
        normalized = str(company_id or "").strip()
        if not normalized:
            raise AdminKnowledgeLifecycleError("Идентификатор компании обязателен.")
        return normalized

    def _normalize_document_id(self, document_id: str) -> str:
        normalized = str(document_id or "").strip()
        if not normalized:
            raise AdminKnowledgeLifecycleError("Идентификатор документа обязателен.")
        if "/" in normalized or "\\" in normalized:
            raise AdminKnowledgeLifecycleError("Недопустимый идентификатор документа.")
        if normalized in (".", ".."):
            raise AdminKnowledgeLifecycleError("Недопустимый идентификатор документа.")
        return normalized
