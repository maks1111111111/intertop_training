"""Tests for knowledge_document_repository."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.knowledge.models import KnowledgeDocumentStatus, KnowledgeSourceType
from app.repositories import knowledge_document_repository


class KnowledgeDocumentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)

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
        extracted_text: str = "",
    ):
        return knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=original_filename,
            source_type=source_type,
            source_language=source_language,
            extracted_text=extracted_text,
        )

    def test_create_document_returns_model(self) -> None:
        document = self._create_document()

        self.assertIsInstance(document.id, int)
        self.assertEqual(document.company_id, "company-a")
        self.assertEqual(document.title, "Safety Manual")
        self.assertEqual(document.original_filename, "manual.pdf")
        self.assertEqual(document.source_type, KnowledgeSourceType.PDF)

    def test_document_id_generated_and_non_empty(self) -> None:
        first = self._create_document(title="First")
        second = self._create_document(title="Second")

        self.assertTrue(first.document_id)
        self.assertTrue(second.document_id)
        self.assertNotEqual(first.document_id, second.document_id)

    def test_initial_status_draft(self) -> None:
        document = self._create_document()

        self.assertEqual(document.status, KnowledgeDocumentStatus.DRAFT)

    def test_initial_version_one(self) -> None:
        document = self._create_document()

        self.assertEqual(document.version, 1)

    def test_source_language_default_auto(self) -> None:
        document = self._create_document()

        self.assertEqual(document.source_language, "auto")

    def test_extracted_text_default_empty(self) -> None:
        document = self._create_document()

        self.assertEqual(document.extracted_text, "")

    def test_created_at_and_updated_at_populated(self) -> None:
        document = self._create_document()

        self.assertTrue(document.created_at)
        self.assertTrue(document.updated_at)

    def test_empty_company_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._create_document(company_id="")

    def test_empty_title_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._create_document(title="   ")

    def test_empty_original_filename_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._create_document(original_filename="")

    def test_unsupported_source_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            knowledge_document_repository.create_document(
                self.db_path,
                company_id="company-a",
                title="Video",
                original_filename="clip.mp4",
                source_type="mp4",
            )

    def test_empty_source_language_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._create_document(source_language="  ")

    def test_same_title_may_exist_in_multiple_companies(self) -> None:
        first = self._create_document(company_id="company-a", title="Shared Title")
        second = self._create_document(company_id="company-b", title="Shared Title")

        self.assertNotEqual(first.document_id, second.document_id)
        self.assertEqual(first.title, second.title)

    def test_list_for_company_returns_only_that_company(self) -> None:
        doc_a = self._create_document(company_id="company-a", title="A Doc")
        self._create_document(company_id="company-b", title="B Doc")

        documents = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-a",
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].document_id, doc_a.document_id)

    def test_get_by_document_id_requires_matching_company_id(self) -> None:
        document = self._create_document(company_id="company-a")

        found = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        missing = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-b",
            document_id=document.document_id,
        )

        self.assertIsNotNone(found)
        self.assertIsNone(missing)

    def test_set_status_cannot_mutate_another_company_document(self) -> None:
        document = self._create_document(company_id="company-a")

        updated = knowledge_document_repository.set_status(
            self.db_path,
            company_id="company-b",
            document_id=document.document_id,
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        self.assertFalse(updated)
        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, KnowledgeDocumentStatus.DRAFT)

    def test_update_extracted_text_cannot_mutate_another_company_document(
        self,
    ) -> None:
        document = self._create_document(company_id="company-a")

        updated = knowledge_document_repository.update_extracted_text(
            self.db_path,
            company_id="company-b",
            document_id=document.document_id,
            extracted_text="foreign text",
        )

        self.assertFalse(updated)
        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.extracted_text, "")

    def test_list_for_company_returns_created_records(self) -> None:
        first = self._create_document(title="First")
        second = self._create_document(title="Second")

        documents = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-a",
        )

        self.assertEqual(len(documents), 2)
        document_ids = {item.document_id for item in documents}
        self.assertEqual(document_ids, {first.document_id, second.document_id})

    def test_list_for_company_status_filter_works(self) -> None:
        draft = self._create_document(title="Draft")
        active_doc = self._create_document(title="Active")
        knowledge_document_repository.set_status(
            self.db_path,
            company_id="company-a",
            document_id=active_doc.document_id,
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        draft_only = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-a",
            status=KnowledgeDocumentStatus.DRAFT,
        )
        active_only = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-a",
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        self.assertEqual(len(draft_only), 1)
        self.assertEqual(draft_only[0].document_id, draft.document_id)
        self.assertEqual(len(active_only), 1)
        self.assertEqual(active_only[0].document_id, active_doc.document_id)

    def test_list_for_company_can_filter_archived_records(self) -> None:
        archived = self._create_document(title="Archived")
        knowledge_document_repository.set_status(
            self.db_path,
            company_id="company-a",
            document_id=archived.document_id,
            status=KnowledgeDocumentStatus.ARCHIVED,
        )
        self._create_document(title="Draft")

        archived_only = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-a",
            status=KnowledgeDocumentStatus.ARCHIVED,
        )

        self.assertEqual(len(archived_only), 1)
        self.assertEqual(archived_only[0].document_id, archived.document_id)

    def test_list_for_company_ordering_is_newest_first_then_id(self) -> None:
        first = self._create_document(title="First")
        second = self._create_document(title="Second")

        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                UPDATE knowledge_documents
                SET created_at = '2026-01-01 08:00:00'
                WHERE document_id = ?
                """,
                (first.document_id,),
            )
            connection.execute(
                """
                UPDATE knowledge_documents
                SET created_at = '2026-01-02 08:00:00'
                WHERE document_id = ?
                """,
                (second.document_id,),
            )

        documents = knowledge_document_repository.list_for_company(
            self.db_path,
            company_id="company-a",
        )

        self.assertEqual(documents[0].document_id, second.document_id)
        self.assertEqual(documents[1].document_id, first.document_id)

    def test_update_extracted_text_persists_text(self) -> None:
        document = self._create_document()

        updated = knowledge_document_repository.update_extracted_text(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
            extracted_text="Extracted knowledge text.",
        )
        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )

        self.assertTrue(updated)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.extracted_text, "Extracted knowledge text.")

    def test_update_extracted_text_updates_updated_at(self) -> None:
        document = self._create_document()
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                UPDATE knowledge_documents
                SET updated_at = '2020-01-01 00:00:00'
                WHERE document_id = ?
                """,
                (document.document_id,),
            )

        knowledge_document_repository.update_extracted_text(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
            extracted_text="New text",
        )
        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )

        self.assertIsNotNone(loaded)
        self.assertNotEqual(loaded.updated_at, "2020-01-01 00:00:00")

    def test_set_status_persists_status(self) -> None:
        document = self._create_document()

        updated = knowledge_document_repository.set_status(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
            status=KnowledgeDocumentStatus.ACTIVE,
        )
        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )

        self.assertTrue(updated)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, KnowledgeDocumentStatus.ACTIVE)

    def test_set_status_updates_updated_at(self) -> None:
        document = self._create_document()
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                UPDATE knowledge_documents
                SET updated_at = '2020-01-01 00:00:00'
                WHERE document_id = ?
                """,
                (document.document_id,),
            )

        knowledge_document_repository.set_status(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
            status=KnowledgeDocumentStatus.ARCHIVED,
        )
        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )

        self.assertIsNotNone(loaded)
        self.assertNotEqual(loaded.updated_at, "2020-01-01 00:00:00")

    def test_set_status_unknown_document_returns_false(self) -> None:
        updated = knowledge_document_repository.set_status(
            self.db_path,
            company_id="company-a",
            document_id="missing-doc",
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        self.assertFalse(updated)

    def test_update_extracted_text_unknown_document_returns_false(self) -> None:
        updated = knowledge_document_repository.update_extracted_text(
            self.db_path,
            company_id="company-a",
            document_id="missing-doc",
            extracted_text="text",
        )

        self.assertFalse(updated)

    def test_invalid_status_rejected_before_mutation(self) -> None:
        document = self._create_document()

        with self.assertRaises(ValueError):
            knowledge_document_repository.set_status(
                self.db_path,
                company_id="company-a",
                document_id=document.document_id,
                status="published",
            )

        loaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, KnowledgeDocumentStatus.DRAFT)

    def test_supported_source_types_accepted(self) -> None:
        cases = (
            (KnowledgeSourceType.PDF, "pdf"),
            (KnowledgeSourceType.DOCX, "docx"),
            (KnowledgeSourceType.PPTX, "pptx"),
            ("pdf", "pdf"),
            ("docx", "docx"),
            ("pptx", "pptx"),
        )
        for source_type, expected in cases:
            document = knowledge_document_repository.create_document(
                self.db_path,
                company_id="company-a",
                title=f"Doc {expected}",
                original_filename=f"file.{expected}",
                source_type=source_type,
            )
            self.assertEqual(document.source_type.value, expected)

    def test_initialize_database_still_works(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'courses'
                """
            ).fetchone()

        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
