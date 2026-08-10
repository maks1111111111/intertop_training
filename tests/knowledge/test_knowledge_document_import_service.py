"""Tests for knowledge document import service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.content.import_readers import ImportReader
from app.database.db import get_connection, initialize_database
from app.knowledge.import_service import (
    KnowledgeDocumentImportError,
    KnowledgeDocumentImportRequest,
    KnowledgeDocumentImportService,
)
from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentStatus, KnowledgeSourceType
from app.repositories import knowledge_document_repository


class _FakeReader:
    def __init__(self, text: str = "Extracted knowledge text") -> None:
        self.text = text
        self.called_with: Optional[Path] = None

    def read(self, path: Path) -> str:
        self.called_with = path
        return self.text


class _FailingReader:
    def read(self, path: Path) -> str:
        raise RuntimeError("parser exploded with /secret/path/file.pdf")


class _NonStringReader:
    def read(self, path: Path) -> object:
        return 12345


class KnowledgeDocumentImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = KnowledgeDocumentImportService()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write_source(self, name: str, content: bytes = b"x") -> Path:
        path = Path(self._tmpdir.name) / name
        path.write_bytes(content)
        return path

    def _import(
        self,
        source_path: Path,
        *,
        company_id: str = "company-a",
        title: Optional[str] = None,
        source_language: str = "auto",
        readers: Optional[dict[KnowledgeSourceType, ImportReader]] = None,
    ) -> KnowledgeDocument:
        service = (
            KnowledgeDocumentImportService(readers=readers)
            if readers is not None
            else self.service
        )
        result = service.import_document(
            self.db_path,
            KnowledgeDocumentImportRequest(
                company_id=company_id,
                source_path=source_path,
                title=title,
                source_language=source_language,
            ),
        )
        return result.document

    def _document_count(self) -> int:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_documents"
            ).fetchone()
        return int(row["count"])

    def test_pdf_reader_selected_by_pdf_extension(self) -> None:
        pdf_reader = _FakeReader("PDF text")
        docx_reader = _FakeReader("DOCX text")
        source_path = self._write_source("manual.pdf")

        document = self._import(
            source_path,
            readers={
                KnowledgeSourceType.PDF: pdf_reader,
                KnowledgeSourceType.DOCX: docx_reader,
                KnowledgeSourceType.PPTX: _FakeReader(),
            },
        )

        self.assertEqual(document.source_type, KnowledgeSourceType.PDF)
        self.assertEqual(pdf_reader.called_with, source_path)
        self.assertIsNone(docx_reader.called_with)

    def test_docx_reader_selected_by_docx_extension(self) -> None:
        pdf_reader = _FakeReader()
        docx_reader = _FakeReader("DOCX text")
        source_path = self._write_source("policy.docx")

        document = self._import(
            source_path,
            readers={
                KnowledgeSourceType.PDF: pdf_reader,
                KnowledgeSourceType.DOCX: docx_reader,
                KnowledgeSourceType.PPTX: _FakeReader(),
            },
        )

        self.assertEqual(document.source_type, KnowledgeSourceType.DOCX)
        self.assertEqual(docx_reader.called_with, source_path)
        self.assertIsNone(pdf_reader.called_with)

    def test_pptx_reader_selected_by_pptx_extension(self) -> None:
        pptx_reader = _FakeReader("PPTX text")
        source_path = self._write_source("slides.pptx")

        document = self._import(
            source_path,
            readers={
                KnowledgeSourceType.PDF: _FakeReader(),
                KnowledgeSourceType.DOCX: _FakeReader(),
                KnowledgeSourceType.PPTX: pptx_reader,
            },
        )

        self.assertEqual(document.source_type, KnowledgeSourceType.PPTX)
        self.assertEqual(pptx_reader.called_with, source_path)

    def test_extracted_text_persisted(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader("  Stored knowledge text  "),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertEqual(document.extracted_text, "Stored knowledge text")
        stored = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.extracted_text, "Stored knowledge text")

    def test_returned_document_is_knowledge_document(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertIsInstance(document, KnowledgeDocument)

    def test_company_id_persisted(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(
            source_path,
            company_id="tenant-x",
            readers=readers,
        )

        self.assertEqual(document.company_id, "tenant-x")

    def test_original_filename_is_basename_only(self) -> None:
        source_path = self._write_source("return_policy.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertEqual(document.original_filename, "return_policy.pdf")
        self.assertNotIn(str(source_path.parent), document.original_filename)

    def test_explicit_title_persisted_trimmed(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(
            source_path,
            title="  Safety Manual  ",
            readers=readers,
        )

        self.assertEqual(document.title, "Safety Manual")

    def test_default_title_derived_from_filename_stem(self) -> None:
        source_path = self._write_source("return_policy.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertEqual(document.title, "return_policy")

    def test_source_language_persisted(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(
            source_path,
            source_language="ru",
            readers=readers,
        )

        self.assertEqual(document.source_language, "ru")

    def test_status_remains_draft(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertEqual(document.status, KnowledgeDocumentStatus.DRAFT)

    def test_version_remains_one(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertEqual(document.version, 1)

    def test_empty_extracted_text_allowed(self) -> None:
        source_path = self._write_source("scanned.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader("   "),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        document = self._import(source_path, readers=readers)

        self.assertEqual(document.extracted_text, "")

    def test_empty_company_id_rejected(self) -> None:
        source_path = self._write_source("manual.pdf")

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, company_id="   ")

        self.assertEqual(ctx.exception.message, "Идентификатор компании обязателен.")

    def test_missing_file_rejected(self) -> None:
        source_path = Path(self._tmpdir.name) / "missing.pdf"

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path)

        self.assertEqual(ctx.exception.message, "Исходный файл не найден.")

    def test_directory_path_rejected(self) -> None:
        source_path = Path(self._tmpdir.name)

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path)

        self.assertEqual(
            ctx.exception.message,
            "Исходный путь должен указывать на файл.",
        )

    def test_mp4_rejected(self) -> None:
        source_path = self._write_source("video.mp4")

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path)

        self.assertEqual(
            ctx.exception.message,
            "Формат MP4 не поддерживается для базы знаний.",
        )

    def test_unsupported_extension_rejected(self) -> None:
        source_path = self._write_source("notes.txt")

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path)

        self.assertEqual(ctx.exception.message, "Неподдерживаемый формат документа.")

    def test_no_extension_rejected(self) -> None:
        source_path = self._write_source("manual")

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path)

        self.assertEqual(
            ctx.exception.message,
            "Файл должен иметь расширение .pdf, .docx или .pptx.",
        )

    def test_blank_explicit_title_rejected(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, title="   ", readers=readers)

        self.assertEqual(
            ctx.exception.message,
            "Название документа не может быть пустым.",
        )

    def test_empty_source_language_rejected(self) -> None:
        source_path = self._write_source("manual.pdf")

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, source_language="   ")

        self.assertEqual(
            ctx.exception.message,
            "Язык источника не может быть пустым.",
        )

    def test_reader_exception_becomes_import_error(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FailingReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, readers=readers)

        self.assertEqual(
            ctx.exception.message,
            "Не удалось извлечь текст из документа.",
        )

    def test_raw_exception_message_not_exposed(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FailingReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, readers=readers)

        self.assertNotIn("parser exploded", ctx.exception.message)
        self.assertNotIn("/secret/path", ctx.exception.message)

    def test_absolute_source_path_not_exposed_in_error_message(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FailingReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, readers=readers)

        self.assertNotIn(str(source_path), ctx.exception.message)

    def test_failed_extraction_does_not_create_database_row(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FailingReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        with self.assertRaises(KnowledgeDocumentImportError):
            self._import(source_path, readers=readers)

        self.assertEqual(self._document_count(), 0)

    def test_non_string_reader_result_rejected(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _NonStringReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        with self.assertRaises(KnowledgeDocumentImportError) as ctx:
            self._import(source_path, readers=readers)

        self.assertEqual(
            ctx.exception.message,
            "Не удалось извлечь текст из документа.",
        )
        self.assertEqual(self._document_count(), 0)

    def test_custom_injected_reader_is_used(self) -> None:
        custom_reader = _FakeReader("Custom injected text")
        source_path = self._write_source("manual.pdf")

        document = self._import(
            source_path,
            readers={
                KnowledgeSourceType.PDF: custom_reader,
                KnowledgeSourceType.DOCX: _FakeReader(),
                KnowledgeSourceType.PPTX: _FakeReader(),
            },
        )

        self.assertEqual(document.extracted_text, "Custom injected text")
        self.assertEqual(custom_reader.called_with, source_path)

    def test_unrelated_readers_are_not_called(self) -> None:
        pdf_reader = _FakeReader()
        docx_reader = _FakeReader()
        pptx_reader = _FakeReader()
        source_path = self._write_source("manual.pdf")

        self._import(
            source_path,
            readers={
                KnowledgeSourceType.PDF: pdf_reader,
                KnowledgeSourceType.DOCX: docx_reader,
                KnowledgeSourceType.PPTX: pptx_reader,
            },
        )

        self.assertIsNotNone(pdf_reader.called_with)
        self.assertIsNone(docx_reader.called_with)
        self.assertIsNone(pptx_reader.called_with)

    def test_imported_documents_for_company_a_not_listed_for_company_b(self) -> None:
        source_path = self._write_source("manual.pdf")
        readers = {
            KnowledgeSourceType.PDF: _FakeReader(),
            KnowledgeSourceType.DOCX: _FakeReader(),
            KnowledgeSourceType.PPTX: _FakeReader(),
        }

        self._import(source_path, company_id="company-a", readers=readers)

        company_b_documents = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-b",
        )

        self.assertEqual(company_b_documents, [])


if __name__ == "__main__":
    unittest.main()
