"""Tests for the admin Knowledge Base Web page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import initialize_database
from app.knowledge.models import KnowledgeDocumentStatus, KnowledgeSourceType
from app.repositories import knowledge_document_repository
from tests.web.test_web_ui import _create_test_app


class AdminKnowledgePageTests(unittest.TestCase):
    """Verify the admin Knowledge Base listing page."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _create_document(
        self,
        *,
        company_id: str = "intertop",
        title: str = "Safety Manual",
        original_filename: str = "manual.pdf",
        source_type: KnowledgeSourceType = KnowledgeSourceType.PDF,
        source_language: str = "auto",
        status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.DRAFT,
    ):
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=original_filename,
            source_type=source_type,
            source_language=source_language,
        )
        if status is not KnowledgeDocumentStatus.DRAFT:
            knowledge_document_repository.set_status(
                self.db_path,
                company_id=company_id,
                document_id=document.document_id,
                status=status,
            )
        return document

    def test_knowledge_page_returns_200(self) -> None:
        response = self.client.get("/admin/knowledge")
        self.assertEqual(response.status_code, 200)

    def test_knowledge_page_empty_state(self) -> None:
        response = self.client.get("/admin/knowledge")
        self.assertIn("Документы базы знаний пока отсутствуют.", response.text)

    def test_knowledge_page_renders_document_list(self) -> None:
        self._create_document(
            title="Return Policy",
            original_filename="returns.pdf",
            source_language="ru",
        )

        response = self.client.get("/admin/knowledge")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Return Policy", response.text)
        self.assertIn("returns.pdf", response.text)
        self.assertIn("pdf", response.text)
        self.assertIn("Язык: ru", response.text)
        self.assertIn("Версия: 1", response.text)

    def test_knowledge_page_renders_draft_status_label(self) -> None:
        self._create_document(title="Draft Doc")

        response = self.client.get("/admin/knowledge")

        self.assertIn("Черновик", response.text)
        self.assertIn('admin-status-badge--draft', response.text)

    def test_knowledge_page_renders_active_status_label(self) -> None:
        self._create_document(
            title="Active Doc",
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        response = self.client.get("/admin/knowledge")

        self.assertIn("Активен", response.text)
        self.assertIn('admin-status-badge--active', response.text)

    def test_knowledge_page_renders_archived_status_label(self) -> None:
        self._create_document(
            title="Archived Doc",
            status=KnowledgeDocumentStatus.ARCHIVED,
        )

        response = self.client.get("/admin/knowledge")

        self.assertIn("Архив", response.text)
        self.assertIn('admin-status-badge--archived', response.text)

    def test_knowledge_page_shows_upload_button(self) -> None:
        response = self.client.get("/admin/knowledge")

        self.assertIn("Загрузить документ", response.text)
        self.assertIn('href="/admin/knowledge/upload"', response.text)

    def test_knowledge_page_marks_subnav_as_active(self) -> None:
        response = self.client.get("/admin/knowledge")

        self.assertIn(
            'href="/admin/knowledge" class="admin-subnav-link is-active"',
            response.text,
        )
        self.assertNotIn("admin-subnav-linkis-active", response.text)

    def test_knowledge_page_presentation_regressions_with_documents(self) -> None:
        """Catch known spacing regressions in document metadata."""
        self._create_document(
            title="Return Policy",
            original_filename="returns.pdf",
            source_language="ru",
        )

        response = self.client.get("/admin/knowledge")
        html = response.text

        self.assertIn("Файл: returns.pdf", html)
        self.assertIn("Язык: ru", html)
        self.assertNotIn("Файл:returns.pdf", html)
        self.assertNotIn("Язык:ru", html)
        self.assertNotIn("admin-subnav-linkis-active", html)

    def test_knowledge_page_empty_state_presentation_regressions(self) -> None:
        """Catch known typo regressions in the empty-state message."""
        response = self.client.get("/admin/knowledge")
        html = response.text

        self.assertIn("Документы базы знаний пока отсутствуют.", html)
        self.assertNotIn("Документы базызнаний", html)

    def test_knowledge_page_excludes_other_company_documents(self) -> None:
        self._create_document(company_id="intertop", title="Visible Doc")
        self._create_document(company_id="other-company", title="Hidden Doc")

        response = self.client.get("/admin/knowledge")

        self.assertIn("Visible Doc", response.text)
        self.assertNotIn("Hidden Doc", response.text)

    def test_admin_dashboard_links_to_knowledge_page(self) -> None:
        response = self.client.get("/admin")

        self.assertIn('href="/admin/knowledge"', response.text)
        self.assertIn("База знаний", response.text)

    def test_admin_dashboard_still_works(self) -> None:
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Управление курсами", response.text)


if __name__ == "__main__":
    unittest.main()
