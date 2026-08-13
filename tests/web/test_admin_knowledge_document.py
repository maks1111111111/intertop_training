"""Tests for admin Knowledge Base document detail page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import initialize_database
from app.knowledge.models import KnowledgeSourceType
from app.repositories import knowledge_chunk_repository, knowledge_document_repository
from app.knowledge.models import KnowledgeDocumentChunkInput
from tests.web.test_web_ui import _create_test_app


class AdminKnowledgeDocumentPageTests(unittest.TestCase):
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
        title: str = "Standards",
        extracted_text: str = "Corporate standards text.",
    ):
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename="standards.pdf",
            source_type=KnowledgeSourceType.PDF,
            extracted_text=extracted_text,
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=company_id,
            document_id=document.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text="First chunk text.",
                    start_char=0,
                    end_char=17,
                )
            ],
        )
        return document

    def test_document_page_returns_200(self) -> None:
        document = self._create_document()

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Standards", response.text)
        self.assertIn("First chunk text.", response.text)

    def test_document_page_renders_chunk_cards(self) -> None:
        document = self._create_document()

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        html = response.text
        self.assertIn("admin-knowledge-chunk-card", html)
        self.assertIn("Фрагмент 1", html)
        self.assertIn("Сохранённый фрагмент базы знаний", html)
        self.assertIn('id="chunk-0"', html)
        self.assertIn("admin-knowledge-document-metadata", html)
        self.assertIn("admin-knowledge-document-layout", html)

    def test_document_page_renders_metadata_grid(self) -> None:
        document = self._create_document()

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        html = response.text
        self.assertIn("admin-knowledge-document-metadata-item", html)
        self.assertIn("standards.pdf", html)
        self.assertIn("PDF", html)
        self.assertIn("Черновик", html)

    def test_document_page_long_chunk_has_expand_controls(self) -> None:
        long_text = "Paragraph one.\n\n" + ("Long knowledge fragment line. " * 80)
        document = self._create_document(extracted_text=long_text)
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id="intertop",
            document_id=document.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text=long_text,
                    start_char=0,
                    end_char=len(long_text),
                )
            ],
        )

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        html = response.text
        self.assertIn("admin-knowledge-chunk-card--collapsible", html)
        self.assertIn("admin-knowledge-chunk-toggle", html)
        self.assertIn("Показать полностью", html)
        self.assertIn("admin-knowledge-chunk-fade", html)
        self.assertIn("admin-knowledge-chunk-body-wrap--collapsed", html)

    def test_document_page_short_chunk_has_no_expand_controls(self) -> None:
        document = self._create_document()

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        html = response.text
        self.assertNotIn('class="admin-knowledge-chunk-toggle"', html)
        self.assertNotIn("admin-knowledge-chunk-card--collapsible", html)

    def test_document_page_focus_chunk_query_param(self) -> None:
        document = self._create_document()

        response = self.client.get(
            f"/admin/knowledge/{document.document_id}?chunk=0"
        )

        self.assertIn("admin-knowledge-chunk-card--focus", response.text)

    def test_unknown_document_returns_404(self) -> None:
        response = self.client.get("/admin/knowledge/missing-doc")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Документ не найден", response.text)

    def test_document_from_another_company_is_not_accessible(self) -> None:
        document = self._create_document(company_id="company-b")

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        self.assertEqual(response.status_code, 404)

    def test_document_page_does_not_expose_filesystem_paths(self) -> None:
        document = self._create_document()

        response = self.client.get(f"/admin/knowledge/{document.document_id}")

        self.assertNotIn(str(self.db_path), response.text)
        self.assertNotIn("/Users/", response.text)


if __name__ == "__main__":
    unittest.main()
