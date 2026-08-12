"""Tests for AdminKnowledgeService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.database.db import initialize_database
from app.knowledge.models import KnowledgeDocumentStatus, KnowledgeSourceType
from app.repositories import knowledge_document_repository
from app.web.admin_knowledge_service import (
    AdminKnowledgeDocumentItem,
    AdminKnowledgeError,
    AdminKnowledgeService,
)


class AdminKnowledgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = AdminKnowledgeService(self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_document(
        self,
        *,
        company_id: str = "company-a",
        title: str = "Safety Manual",
        original_filename: str = "manual.pdf",
        source_type: KnowledgeSourceType = KnowledgeSourceType.PDF,
        source_language: str = "auto",
    ):
        return knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=original_filename,
            source_type=source_type,
            source_language=source_language,
        )

    def test_empty_company_returns_empty_tuple(self) -> None:
        result = self.service.get_documents("company-empty")

        self.assertEqual(result, ())

    def test_one_draft_document_maps_all_fields(self) -> None:
        document = self._create_document(
            title="Return Policy",
            original_filename="returns.pdf",
            source_type=KnowledgeSourceType.PDF,
            source_language="ru",
        )

        result = self.service.get_documents("company-a")

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIsInstance(item, AdminKnowledgeDocumentItem)
        self.assertEqual(item.document_id, document.document_id)
        self.assertEqual(item.title, "Return Policy")
        self.assertEqual(item.original_filename, "returns.pdf")
        self.assertEqual(item.source_type, "pdf")
        self.assertEqual(item.source_language, "ru")
        self.assertEqual(item.status, "draft")
        self.assertEqual(item.status_label, "Черновик")
        self.assertEqual(item.version, 1)
        self.assertTrue(item.created_at)

    def test_active_status_label(self) -> None:
        document = self._create_document(title="Active Doc")
        knowledge_document_repository.set_status(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        result = self.service.get_documents("company-a")

        self.assertEqual(result[0].status, "active")
        self.assertEqual(result[0].status_label, "Активен")

    def test_archived_status_label(self) -> None:
        document = self._create_document(title="Archived Doc")
        knowledge_document_repository.set_status(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            status=KnowledgeDocumentStatus.ARCHIVED,
        )

        result = self.service.get_documents("company-a")

        self.assertEqual(result[0].status, "archived")
        self.assertEqual(result[0].status_label, "Архив")

    def test_multiple_documents_preserve_repository_ordering(self) -> None:
        first = self._create_document(title="First")
        second = self._create_document(title="Second")
        third = self._create_document(title="Third")

        result = self.service.get_documents("company-a")

        self.assertEqual(
            [item.document_id for item in result],
            [third.document_id, second.document_id, first.document_id],
        )

    def test_documents_from_another_company_never_appear(self) -> None:
        own = self._create_document(company_id="company-a", title="Own Doc")
        self._create_document(company_id="company-b", title="Other Doc")

        result = self.service.get_documents("company-a")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].document_id, own.document_id)
        self.assertEqual(result[0].title, "Own Doc")

    def test_whitespace_around_company_id_is_normalized(self) -> None:
        document = self._create_document(company_id="company-a", title="Trimmed")

        result = self.service.get_documents("  company-a  ")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].document_id, document.document_id)

    def test_empty_company_id_raises_admin_knowledge_error(self) -> None:
        with self.assertRaises(AdminKnowledgeError) as context:
            self.service.get_documents("")

        self.assertEqual(
            context.exception.message,
            "Идентификатор компании обязателен.",
        )

    def test_whitespace_only_company_id_raises_admin_knowledge_error(self) -> None:
        with self.assertRaises(AdminKnowledgeError) as context:
            self.service.get_documents("   ")

        self.assertEqual(
            context.exception.message,
            "Идентификатор компании обязателен.",
        )

    def test_injected_list_documents_dependency_is_used(self) -> None:
        captured: dict[str, Optional[str]] = {"company_id": None}

        def fake_list(
            db_path: Path,
            *,
            company_id: str,
            status=None,
        ):
            captured["company_id"] = company_id
            return []

        service = AdminKnowledgeService(
            self.db_path,
            list_documents=fake_list,
        )

        service.get_documents("  tenant-x  ")

        self.assertEqual(captured["company_id"], "tenant-x")


if __name__ == "__main__":
    unittest.main()
