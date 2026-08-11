"""Knowledge Base document lifecycle service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.repositories import knowledge_document_repository

_logger = logging.getLogger(__name__)

GetDocumentFn = Callable[..., Optional[KnowledgeDocument]]
SetStatusFn = Callable[..., bool]


class KnowledgeDocumentLifecycleError(Exception):
    """Raised when a knowledge document lifecycle transition cannot be applied."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class KnowledgeDocumentLifecycleService:
    """Validate and apply business-level knowledge document status transitions."""

    def __init__(
        self,
        *,
        get_document: Optional[GetDocumentFn] = None,
        set_status: Optional[SetStatusFn] = None,
    ) -> None:
        self._get_document = get_document or knowledge_document_repository.get_by_document_id
        self._set_status = set_status or knowledge_document_repository.set_status

    def publish(
        self,
        db_path: Path,
        *,
        company_id: str,
        document_id: str,
    ) -> KnowledgeDocument:
        """Publish a draft document or return an already active document."""
        document = self._load_document(
            db_path,
            company_id=company_id,
            document_id=document_id,
        )

        if document.status == KnowledgeDocumentStatus.ACTIVE:
            return document

        if document.status == KnowledgeDocumentStatus.ARCHIVED:
            raise KnowledgeDocumentLifecycleError(
                "Archived knowledge documents cannot be published."
            )

        return self._apply_status_change(
            db_path,
            company_id=company_id,
            document_id=document_id,
            target_status=KnowledgeDocumentStatus.ACTIVE,
        )

    def archive(
        self,
        db_path: Path,
        *,
        company_id: str,
        document_id: str,
    ) -> KnowledgeDocument:
        """Archive a draft or active document, or return an already archived document."""
        document = self._load_document(
            db_path,
            company_id=company_id,
            document_id=document_id,
        )

        if document.status == KnowledgeDocumentStatus.ARCHIVED:
            return document

        return self._apply_status_change(
            db_path,
            company_id=company_id,
            document_id=document_id,
            target_status=KnowledgeDocumentStatus.ARCHIVED,
        )

    def _load_document(
        self,
        db_path: Path,
        *,
        company_id: str,
        document_id: str,
    ) -> KnowledgeDocument:
        try:
            document = self._get_document(
                db_path,
                company_id=company_id,
                document_id=document_id,
            )
        except ValueError as exc:
            raise KnowledgeDocumentLifecycleError(
                "Knowledge document not found."
            ) from exc

        if document is None:
            raise KnowledgeDocumentLifecycleError(
                "Knowledge document not found."
            )

        return document

    def _apply_status_change(
        self,
        db_path: Path,
        *,
        company_id: str,
        document_id: str,
        target_status: KnowledgeDocumentStatus,
    ) -> KnowledgeDocument:
        updated = self._set_status(
            db_path,
            company_id=company_id,
            document_id=document_id,
            status=target_status,
        )
        if not updated:
            _logger.error(
                "Failed to update knowledge document status to %s",
                target_status.value,
            )
            raise KnowledgeDocumentLifecycleError(
                "Failed to update knowledge document status."
            )

        reloaded = self._get_document(
            db_path,
            company_id=company_id,
            document_id=document_id,
        )
        if reloaded is None:
            _logger.error(
                "Knowledge document disappeared after status update"
            )
            raise KnowledgeDocumentLifecycleError(
                "Failed to update knowledge document status."
            )

        if reloaded.status != target_status:
            _logger.error(
                "Knowledge document status mismatch after update: expected %s, got %s",
                target_status.value,
                reloaded.status.value,
            )
            raise KnowledgeDocumentLifecycleError(
                "Failed to update knowledge document status."
            )

        return reloaded
