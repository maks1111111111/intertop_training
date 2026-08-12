"""Safe Knowledge Base document upload and import for the Web admin."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.knowledge.import_service import (
    KnowledgeDocumentImportError,
    KnowledgeDocumentImportRequest,
    KnowledgeDocumentImportResult,
    KnowledgeDocumentImportService,
)
from app.knowledge.models import KnowledgeDocument

_logger = logging.getLogger(__name__)

_KNOWLEDGE_UPLOAD_SUBDIR = "knowledge"
_SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx"})
_ALLOWED_SOURCE_LANGUAGES = frozenset({"auto", "ru", "kk", "en"})


class AdminKnowledgeUploadError(Exception):
    """Raised when a Knowledge Base upload fails validation or import."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminKnowledgeUploadResult:
    """Result of a successful Knowledge Base document upload and import."""

    document: KnowledgeDocument
    chunk_count: int


def _validate_upload_filename(name: str) -> str:
    """Return the original basename when safe; reject traversal-like names."""
    raw = str(name).strip()
    if not raw:
        raise AdminKnowledgeUploadError(
            "Файл не выбран. Загрузите документ."
        )
    if "/" in raw or "\\" in raw:
        raise AdminKnowledgeUploadError("Недопустимое имя файла.")
    if raw in (".", ".."):
        raise AdminKnowledgeUploadError("Недопустимое имя файла.")
    return raw


def _knowledge_upload_root(upload_dir: Path) -> Path:
    return upload_dir / _KNOWLEDGE_UPLOAD_SUBDIR


class AdminKnowledgeUploadService:
    """Validate uploads, stage source files, and import Knowledge Base documents."""

    def __init__(
        self,
        db_path: Path,
        upload_dir: Path,
        *,
        import_service: Optional[KnowledgeDocumentImportService] = None,
        import_document: Optional[
            Callable[..., KnowledgeDocumentImportResult]
        ] = None,
    ) -> None:
        self._db_path = db_path
        self._upload_dir = upload_dir
        self._import_service = import_service or KnowledgeDocumentImportService()
        if import_document is not None:
            self._import_document = import_document
        else:
            self._import_document = self._import_service.import_document

    def import_upload(
        self,
        *,
        company_id: str,
        filename: Optional[str],
        content: bytes,
        title: Optional[str] = None,
        source_language: str = "auto",
    ) -> AdminKnowledgeUploadResult:
        """Validate, stage, import, and clean up one uploaded Knowledge Base file."""
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise AdminKnowledgeUploadError("Идентификатор компании обязателен.")

        if not content:
            raise AdminKnowledgeUploadError(
                "Файл пуст. Загрузите документ."
            )

        original_filename = _validate_upload_filename(str(filename or ""))
        extension = Path(original_filename).suffix.lower()
        if extension not in _SUPPORTED_EXTENSIONS:
            raise AdminKnowledgeUploadError(
                "Неподдерживаемый формат файла. Допустимые форматы: PDF, DOCX, PPTX."
            )

        normalized_language = str(source_language or "auto").strip()
        if normalized_language not in _ALLOWED_SOURCE_LANGUAGES:
            raise AdminKnowledgeUploadError(
                "Некорректный язык источника."
            )

        normalized_title: Optional[str] = None
        if title is not None:
            stripped_title = str(title).strip()
            if stripped_title:
                normalized_title = stripped_title

        staging_dir: Optional[Path] = None
        try:
            staging_dir = self._stage_upload(original_filename, content)
            source_path = staging_dir / original_filename
            import_result = self._import_document(
                self._db_path,
                KnowledgeDocumentImportRequest(
                    company_id=normalized_company_id,
                    source_path=source_path,
                    title=normalized_title,
                    source_language=normalized_language,
                ),
            )
        except KnowledgeDocumentImportError as exc:
            raise AdminKnowledgeUploadError(exc.message) from exc
        except AdminKnowledgeUploadError:
            raise
        except Exception:
            _logger.exception("Unexpected failure importing knowledge document")
            raise AdminKnowledgeUploadError(
                "Не удалось импортировать документ."
            )
        finally:
            if staging_dir is not None:
                self._cleanup_staging_dir(staging_dir)

        return AdminKnowledgeUploadResult(
            document=import_result.document,
            chunk_count=len(import_result.chunks),
        )

    def _stage_upload(self, original_filename: str, content: bytes) -> Path:
        """Persist uploaded bytes under a unique staging directory."""
        upload_root = _knowledge_upload_root(self._upload_dir)
        staging_dir: Optional[Path] = None
        try:
            upload_root.mkdir(parents=True, exist_ok=True)

            staging_dir = (upload_root / uuid.uuid4().hex).resolve()
            upload_root_resolved = upload_root.resolve()
            if os.path.commonpath(
                [str(staging_dir), str(upload_root_resolved)]
            ) != str(upload_root_resolved):
                raise AdminKnowledgeUploadError("Недопустимое имя файла.")

            staging_dir.mkdir(parents=False, exist_ok=False)

            stored_path = (staging_dir / original_filename).resolve()
            if os.path.commonpath([str(stored_path), str(staging_dir)]) != str(
                staging_dir
            ):
                raise AdminKnowledgeUploadError("Недопустимое имя файла.")

            if stored_path.exists():
                raise AdminKnowledgeUploadError(
                    "Не удалось сохранить файл. Попробуйте ещё раз."
                )

            stored_path.write_bytes(content)
            return staging_dir
        except AdminKnowledgeUploadError:
            if staging_dir is not None:
                self._cleanup_staging_dir(staging_dir)
            raise
        except OSError:
            _logger.exception("Failed to stage knowledge upload file")
            if staging_dir is not None:
                self._cleanup_staging_dir(staging_dir)
            raise AdminKnowledgeUploadError(
                "Не удалось сохранить файл. Попробуйте ещё раз."
            ) from None

    @staticmethod
    def _cleanup_staging_dir(staging_dir: Path) -> None:
        """Remove a staging directory and its contents."""
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
        except OSError:
            _logger.exception(
                "Failed to clean up staged knowledge upload directory"
            )
