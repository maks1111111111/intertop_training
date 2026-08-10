"""Knowledge Base document import service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from app.content.docx_reader import DocxReader
from app.content.import_readers import ImportReader
from app.content.pdf_reader import PdfReader
from app.content.pptx_reader import PptxReader
from app.database.db import get_connection
from app.knowledge.chunking import KnowledgeTextChunker
from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentChunk, KnowledgeSourceType
from app.repositories import knowledge_chunk_repository, knowledge_document_repository

_logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS: dict[str, KnowledgeSourceType] = {
    ".pdf": KnowledgeSourceType.PDF,
    ".docx": KnowledgeSourceType.DOCX,
    ".pptx": KnowledgeSourceType.PPTX,
}


class KnowledgeDocumentImportError(Exception):
    """Raised when a knowledge document cannot be imported safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class KnowledgeDocumentImportRequest:
    company_id: str
    source_path: Path
    title: Optional[str] = None
    source_language: str = "auto"


@dataclass(frozen=True)
class KnowledgeDocumentImportResult:
    document: KnowledgeDocument
    chunks: tuple[KnowledgeDocumentChunk, ...]


def _default_readers() -> dict[KnowledgeSourceType, ImportReader]:
    return {
        KnowledgeSourceType.PDF: PdfReader(),
        KnowledgeSourceType.DOCX: DocxReader(),
        KnowledgeSourceType.PPTX: PptxReader(),
    }


def _detect_source_type(path: Path) -> KnowledgeSourceType:
    extension = path.suffix.lower()
    source_type = _SUPPORTED_EXTENSIONS.get(extension)
    if source_type is None:
        if extension == ".mp4":
            raise KnowledgeDocumentImportError(
                "Формат MP4 не поддерживается для базы знаний."
            )
        if not extension:
            raise KnowledgeDocumentImportError(
                "Файл должен иметь расширение .pdf, .docx или .pptx."
            )
        raise KnowledgeDocumentImportError(
            "Неподдерживаемый формат документа."
        )
    return source_type


def _normalize_extracted_text(text: object) -> str:
    if not isinstance(text, str):
        raise KnowledgeDocumentImportError(
            "Не удалось извлечь текст из документа."
        )
    return text.strip()


def _resolve_title(request: KnowledgeDocumentImportRequest, source_path: Path) -> str:
    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise KnowledgeDocumentImportError(
                "Название документа не может быть пустым."
            )
        return title

    stem = source_path.stem.strip()
    if not stem:
        raise KnowledgeDocumentImportError(
            "Название документа не может быть пустым."
        )
    return stem


def _rollback_imported_document(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
) -> None:
    """Remove a partially imported document after chunk persistence failure."""
    try:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                DELETE FROM knowledge_document_chunks
                WHERE company_id = ?
                  AND document_id = ?
                """,
                (company_id, document_id),
            )
            connection.execute(
                """
                DELETE FROM knowledge_documents
                WHERE company_id = ?
                  AND document_id = ?
                """,
                (company_id, document_id),
            )
    except Exception:
        _logger.exception(
            "Failed to roll back partially imported knowledge document"
        )


class KnowledgeDocumentImportService:
    """Import corporate Knowledge Base documents from local source files."""

    def __init__(
        self,
        readers: Optional[Mapping[KnowledgeSourceType, ImportReader]] = None,
        chunker: Optional[KnowledgeTextChunker] = None,
    ) -> None:
        self._readers = (
            dict(readers) if readers is not None else _default_readers()
        )
        self._chunker = chunker or KnowledgeTextChunker()

    def import_document(
        self,
        db_path: Path,
        request: KnowledgeDocumentImportRequest,
    ) -> KnowledgeDocumentImportResult:
        company_id = request.company_id.strip()
        if not company_id:
            raise KnowledgeDocumentImportError(
                "Идентификатор компании обязателен."
            )

        source_language = request.source_language.strip()
        if not source_language:
            raise KnowledgeDocumentImportError(
                "Язык источника не может быть пустым."
            )

        source_path = request.source_path
        if not source_path.exists():
            raise KnowledgeDocumentImportError("Исходный файл не найден.")
        if not source_path.is_file():
            raise KnowledgeDocumentImportError(
                "Исходный путь должен указывать на файл."
            )

        source_type = _detect_source_type(source_path)
        title = _resolve_title(request, source_path)
        original_filename = source_path.name

        reader = self._readers.get(source_type)
        if reader is None:
            raise KnowledgeDocumentImportError(
                "Не удалось извлечь текст из документа."
            )

        try:
            extracted_text = _normalize_extracted_text(reader.read(source_path))
        except KnowledgeDocumentImportError:
            raise
        except Exception:
            _logger.exception(
                "Failed to extract text from knowledge document source"
            )
            raise KnowledgeDocumentImportError(
                "Не удалось извлечь текст из документа."
            )

        try:
            document = knowledge_document_repository.create_document(
                db_path,
                company_id=company_id,
                title=title,
                original_filename=original_filename,
                source_type=source_type,
                source_language=source_language,
                extracted_text=extracted_text,
            )
        except ValueError:
            _logger.exception("Failed to create knowledge document")
            raise KnowledgeDocumentImportError(
                "Не удалось сохранить документ."
            )

        chunks = self._chunker.chunk(extracted_text)

        try:
            knowledge_chunk_repository.replace_document_chunks(
                db_path,
                company_id=document.company_id,
                document_id=document.document_id,
                chunks=chunks,
            )
        except Exception:
            _logger.exception(
                "Failed to persist knowledge document chunks after import"
            )
            _rollback_imported_document(
                db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )
            raise KnowledgeDocumentImportError(
                "Не удалось сохранить фрагменты документа."
            )

        stored_chunks = tuple(
            knowledge_chunk_repository.list_for_document(
                db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )
        )

        return KnowledgeDocumentImportResult(
            document=document,
            chunks=stored_chunks,
        )
