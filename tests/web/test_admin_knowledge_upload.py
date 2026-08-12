"""Tests for admin Knowledge Base document upload and import."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest import mock

from fastapi.testclient import TestClient

from app.content.import_readers import ImportReader
from app.database.db import initialize_database
from app.knowledge.import_service import (
    KnowledgeDocumentImportError,
    KnowledgeDocumentImportRequest,
    KnowledgeDocumentImportResult,
    KnowledgeDocumentImportService,
)
from app.knowledge.models import KnowledgeDocument, KnowledgeSourceType
from app.repositories import knowledge_chunk_repository, knowledge_document_repository
from app.web.admin_knowledge_upload_service import (
    AdminKnowledgeUploadError,
    AdminKnowledgeUploadService,
)
from tests.web.test_web_ui import _create_test_app


class _FakeReader:
    def __init__(self, text: str = "Knowledge base extracted text for testing.") -> None:
        self.text = text

    def read(self, path: Path) -> str:
        return self.text


@dataclass(frozen=True)
class _RecordedImportCall:
    company_id: str
    source_path: Path
    title: Optional[str]
    source_language: str


class _RecordingImportService:
    def __init__(
        self,
        *,
        result: Optional[KnowledgeDocumentImportResult] = None,
        error: Optional[KnowledgeDocumentImportError] = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[_RecordedImportCall] = []

    def import_document(
        self,
        db_path: Path,
        request: KnowledgeDocumentImportRequest,
    ) -> KnowledgeDocumentImportResult:
        self.calls.append(
            _RecordedImportCall(
                company_id=request.company_id,
                source_path=request.source_path,
                title=request.title,
                source_language=request.source_language,
            )
        )
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("Recording import service requires result or error")
        return self.result


class AdminKnowledgeUploadServiceTests(unittest.TestCase):
    """Direct tests for AdminKnowledgeUploadService staging and cleanup."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.tmp.name) / "uploads"
        self.upload_dir.mkdir()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        readers = {
            KnowledgeSourceType.PDF: _FakeReader("Long knowledge text " * 20),
            KnowledgeSourceType.DOCX: _FakeReader("DOCX knowledge text"),
            KnowledgeSourceType.PPTX: _FakeReader("PPTX knowledge text"),
        }
        self.import_service = KnowledgeDocumentImportService(readers=readers)
        self.service = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_service=self.import_service,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _knowledge_root(self) -> Path:
        return self.upload_dir / "knowledge"

    def test_valid_pdf_import_persists_document(self) -> None:
        result = self.service.import_upload(
            company_id="intertop",
            filename="policy.pdf",
            content=b"%PDF-1.4 test",
            title="Return Policy",
            source_language="ru",
        )

        self.assertEqual(result.document.company_id, "intertop")
        self.assertEqual(result.document.title, "Return Policy")
        self.assertEqual(result.document.original_filename, "policy.pdf")
        self.assertEqual(result.document.source_language, "ru")
        self.assertGreater(result.chunk_count, 0)

    def test_default_title_from_filename_stem(self) -> None:
        result = self.service.import_upload(
            company_id="intertop",
            filename="return_policy.pdf",
            content=b"%PDF-1.4 test",
        )

        self.assertEqual(result.document.title, "return_policy")
        self.assertEqual(result.document.original_filename, "return_policy.pdf")

    def test_staging_directory_cleaned_up_after_success(self) -> None:
        self.service.import_upload(
            company_id="intertop",
            filename="policy.pdf",
            content=b"%PDF-1.4 test",
        )

        knowledge_root = self._knowledge_root()
        if knowledge_root.exists():
            self.assertEqual(list(knowledge_root.iterdir()), [])

    def test_staging_directory_cleaned_up_after_import_failure(self) -> None:
        failing = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_document=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                KnowledgeDocumentImportError("Не удалось извлечь текст из документа.")
            ),
        )

        with self.assertRaises(AdminKnowledgeUploadError):
            failing.import_upload(
                company_id="intertop",
                filename="policy.pdf",
                content=b"%PDF-1.4 test",
            )

        knowledge_root = self._knowledge_root()
        if knowledge_root.exists():
            self.assertEqual(list(knowledge_root.iterdir()), [])

    def test_unsupported_extension_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeUploadError) as context:
            self.service.import_upload(
                company_id="intertop",
                filename="notes.txt",
                content=b"plain text",
            )

        self.assertIn("Неподдерживаемый формат", context.exception.message)

    def test_empty_file_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeUploadError) as context:
            self.service.import_upload(
                company_id="intertop",
                filename="empty.pdf",
                content=b"",
            )

        self.assertIn("Файл пуст", context.exception.message)

    def test_filename_with_spaces_preserved_exactly(self) -> None:
        filename = "Return Policy Manual.pdf"
        result = self.service.import_upload(
            company_id="intertop",
            filename=filename,
            content=b"%PDF-1.4 test",
        )

        self.assertEqual(result.document.original_filename, filename)

    def test_cyrillic_filename_preserved_exactly(self) -> None:
        filename = "Регламент возврата товара.pdf"
        result = self.service.import_upload(
            company_id="intertop",
            filename=filename,
            content=b"%PDF-1.4 test",
        )

        self.assertEqual(result.document.original_filename, filename)
        self.assertEqual(result.document.title, "Регламент возврата товара")

    def test_path_traversal_filename_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeUploadError) as context:
            self.service.import_upload(
                company_id="intertop",
                filename="../../manual.pdf",
                content=b"%PDF traversal",
            )

        self.assertEqual(context.exception.message, "Недопустимое имя файла.")

    def test_backslash_path_traversal_filename_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeUploadError) as context:
            self.service.import_upload(
                company_id="intertop",
                filename="..\\manual.pdf",
                content=b"%PDF traversal",
            )

        self.assertEqual(context.exception.message, "Недопустимое имя файла.")

    def test_staging_write_failure_maps_to_safe_error(self) -> None:
        with mock.patch.object(
            Path,
            "write_bytes",
            side_effect=OSError("simulated write failure"),
        ):
            with self.assertRaises(AdminKnowledgeUploadError) as context:
                self.service.import_upload(
                    company_id="intertop",
                    filename="policy.pdf",
                    content=b"%PDF-1.4 test",
                )

        self.assertEqual(
            context.exception.message,
            "Не удалось сохранить файл. Попробуйте ещё раз.",
        )
        knowledge_root = self._knowledge_root()
        if knowledge_root.exists():
            self.assertEqual(list(knowledge_root.iterdir()), [])

    def test_staging_root_creation_failure_maps_to_safe_error(self) -> None:
        service = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_document=lambda *_args, **_kwargs: self.fail(
                "Import must not run when staging root creation fails"
            ),
        )
        upload_root = self.upload_dir / "knowledge"
        upload_root.mkdir()
        upload_root.chmod(0o500)

        try:
            with self.assertRaises(AdminKnowledgeUploadError) as context:
                service.import_upload(
                    company_id="intertop",
                    filename="policy.pdf",
                    content=b"%PDF-1.4 test",
                )
        finally:
            upload_root.chmod(0o700)

        self.assertEqual(
            context.exception.message,
            "Не удалось сохранить файл. Попробуйте ещё раз.",
        )


class AdminKnowledgeUploadRouteTests(unittest.TestCase):
    """HTTP tests for Knowledge Base upload routes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)
        self.upload_dir = self.app.state.upload_dir

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _make_import_result(
        self,
        *,
        company_id: str = "intertop",
        title: str = "Imported Doc",
        original_filename: str = "source.pdf",
        source_language: str = "auto",
    ) -> KnowledgeDocumentImportResult:
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=original_filename,
            source_type=KnowledgeSourceType.PDF,
            source_language=source_language,
            extracted_text="chunkable text " * 10,
        )
        chunks = tuple(
            knowledge_chunk_repository.list_for_document(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )
        )
        return KnowledgeDocumentImportResult(document=document, chunks=chunks)

    def _install_recording_service(
        self,
        *,
        result: Optional[KnowledgeDocumentImportResult] = None,
        error: Optional[KnowledgeDocumentImportError] = None,
    ) -> _RecordingImportService:
        recording = _RecordingImportService(result=result, error=error)
        self.app.state.admin_knowledge_upload_service = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_document=recording.import_document,
        )
        return recording

    def test_upload_page_returns_200(self) -> None:
        response = self.client.get("/admin/knowledge/upload")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Загрузить документ", response.text)
        self.assertIn("PDF, DOCX, PPTX", response.text)
        self.assertIn(
            "Импортируйте корпоративный документ в базу знаний.",
            response.text,
        )

    def test_upload_page_marks_knowledge_subnav_as_active(self) -> None:
        response = self.client.get("/admin/knowledge/upload")

        self.assertIn(
            'href="/admin/knowledge" class="admin-subnav-link is-active"',
            response.text,
        )
        self.assertNotIn("admin-subnav-linkis-active", response.text)

    def test_upload_form_posts_to_upload_route(self) -> None:
        response = self.client.get("/admin/knowledge/upload")
        self.assertIn('action="/admin/knowledge/upload"', response.text)
        self.assertIn('enctype="multipart/form-data"', response.text)

    def test_knowledge_page_upload_button_links_to_upload_route(self) -> None:
        response = self.client.get("/admin/knowledge")
        self.assertIn('href="/admin/knowledge/upload"', response.text)

    def test_valid_pdf_upload_redirects_to_knowledge_list(self) -> None:
        self._install_recording_service(
            result=self._make_import_result(title="Safety Manual"),
        )

        response = self.client.post(
            "/admin/knowledge/upload",
            data={"title": "Safety Manual", "source_language": "ru"},
            files={"source_file": ("manual.pdf", b"%PDF test", "application/pdf")},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/knowledge")

    def test_imported_document_visible_on_knowledge_page(self) -> None:
        readers = {KnowledgeSourceType.PDF: _FakeReader("Visible imported text")}
        self.app.state.admin_knowledge_upload_service = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_service=KnowledgeDocumentImportService(readers=readers),
        )

        response = self.client.post(
            "/admin/knowledge/upload",
            data={"title": "Visible Manual", "source_language": "ru"},
            files={"source_file": ("manual.pdf", b"%PDF test", "application/pdf")},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        list_response = self.client.get("/admin/knowledge")
        self.assertIn("Visible Manual", list_response.text)
        self.assertIn("manual.pdf", list_response.text)

    def test_post_uses_centralized_company_id(self) -> None:
        recording = self._install_recording_service(
            result=self._make_import_result(),
        )

        self.client.post(
            "/admin/knowledge/upload",
            data={
                "company_id": "attacker-company",
                "title": "Ignored Company",
                "source_language": "auto",
            },
            files={"source_file": ("manual.pdf", b"%PDF test", "application/pdf")},
        )

        self.assertEqual(len(recording.calls), 1)
        self.assertEqual(recording.calls[0].company_id, "intertop")

    def test_explicit_title_forwarded_to_import(self) -> None:
        recording = self._install_recording_service(
            result=self._make_import_result(title="Explicit Title"),
        )

        self.client.post(
            "/admin/knowledge/upload",
            data={"title": "Explicit Title", "source_language": "auto"},
            files={"source_file": ("manual.pdf", b"%PDF test", "application/pdf")},
        )

        self.assertEqual(recording.calls[0].title, "Explicit Title")

    def test_blank_title_forwarded_as_none(self) -> None:
        recording = self._install_recording_service(
            result=self._make_import_result(title="manual"),
        )

        self.client.post(
            "/admin/knowledge/upload",
            data={"title": "   ", "source_language": "auto"},
            files={"source_file": ("manual.pdf", b"%PDF test", "application/pdf")},
        )

        self.assertIsNone(recording.calls[0].title)

    def test_source_language_forwarded(self) -> None:
        recording = self._install_recording_service(
            result=self._make_import_result(source_language="kk"),
        )

        self.client.post(
            "/admin/knowledge/upload",
            data={"source_language": "kk"},
            files={"source_file": ("manual.pdf", b"%PDF test", "application/pdf")},
        )

        self.assertEqual(recording.calls[0].source_language, "kk")

    def test_missing_file_shows_error(self) -> None:
        response = self.client.post(
            "/admin/knowledge/upload",
            data={"title": "No File", "source_language": "auto"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Файл не выбран", response.text)
        self.assertIn("No File", response.text)

    def test_empty_file_shows_error(self) -> None:
        response = self.client.post(
            "/admin/knowledge/upload",
            data={"source_language": "auto"},
            files={"source_file": ("empty.pdf", b"", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Файл пуст", response.text)

    def test_unsupported_extension_shows_error(self) -> None:
        response = self.client.post(
            "/admin/knowledge/upload",
            data={"source_language": "auto"},
            files={"source_file": ("notes.txt", b"plain", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Неподдерживаемый формат", response.text)

    def test_import_error_rendered_safely(self) -> None:
        self._install_recording_service(
            error=KnowledgeDocumentImportError(
                "Не удалось извлечь текст из документа."
            ),
        )

        response = self.client.post(
            "/admin/knowledge/upload",
            data={"title": "Broken", "source_language": "auto"},
            files={"source_file": ("broken.pdf", b"%PDF", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось извлечь текст из документа.", response.text)
        self.assertNotIn("/Users/", response.text)
        self.assertNotIn("Traceback", response.text)

    def test_failed_import_does_not_leave_staged_files(self) -> None:
        self._install_recording_service(
            error=KnowledgeDocumentImportError(
                "Не удалось извлечь текст из документа."
            ),
        )

        self.client.post(
            "/admin/knowledge/upload",
            data={"source_language": "auto"},
            files={"source_file": ("broken.pdf", b"%PDF", "application/pdf")},
        )

        knowledge_root = self.upload_dir / "knowledge"
        if knowledge_root.exists():
            self.assertEqual(list(knowledge_root.iterdir()), [])

    def test_real_import_persists_chunks(self) -> None:
        readers = {KnowledgeSourceType.PDF: _FakeReader("Chunkable " * 30)}
        self.app.state.admin_knowledge_upload_service = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_service=KnowledgeDocumentImportService(readers=readers),
        )

        response = self.client.post(
            "/admin/knowledge/upload",
            data={"title": "Chunked Doc", "source_language": "auto"},
            files={"source_file": ("chunked.pdf", b"%PDF", "application/pdf")},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        documents = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="intertop",
        )
        self.assertEqual(len(documents), 1)
        chunk_count = knowledge_chunk_repository.count_for_document(
            self.db_path,
            company_id="intertop",
            document_id=documents[0].document_id,
        )
        self.assertGreater(chunk_count, 0)

    def test_successful_upload_cleans_staging_files(self) -> None:
        readers = {KnowledgeSourceType.PDF: _FakeReader("Cleanup test text")}
        self.app.state.admin_knowledge_upload_service = AdminKnowledgeUploadService(
            self.db_path,
            self.upload_dir,
            import_service=KnowledgeDocumentImportService(readers=readers),
        )

        self.client.post(
            "/admin/knowledge/upload",
            data={"source_language": "auto"},
            files={"source_file": ("cleanup.pdf", b"%PDF", "application/pdf")},
        )

        knowledge_root = self.upload_dir / "knowledge"
        if knowledge_root.exists():
            self.assertEqual(list(knowledge_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
