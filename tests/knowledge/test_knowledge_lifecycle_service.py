"""Tests for knowledge document lifecycle service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from app.database.db import initialize_database
from app.knowledge.lifecycle_service import (
    KnowledgeDocumentLifecycleError,
    KnowledgeDocumentLifecycleService,
)
from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.knowledge.retrieval import KnowledgeChunkRetrievalService
from app.knowledge.models import KnowledgeDocumentChunkInput
from app.repositories import knowledge_chunk_repository, knowledge_document_repository


class KnowledgeDocumentLifecycleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = KnowledgeDocumentLifecycleService()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_document(
        self,
        *,
        company_id: str = "company-a",
        title: str = "Policy",
        filename: str = "policy.pdf",
        extracted_text: str = "Company return policy details.",
    ) -> KnowledgeDocument:
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=filename,
            source_type="pdf",
            extracted_text=extracted_text,
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text=extracted_text,
                    start_char=0,
                    end_char=len(extracted_text),
                )
            ],
        )
        return document

    def test_publish_draft_becomes_active(self) -> None:
        document = self._create_document()

        published = self.service.publish(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )

        self.assertEqual(published.status, KnowledgeDocumentStatus.ACTIVE)
        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.ACTIVE)

    def test_publish_active_is_idempotent(self) -> None:
        document = self._create_document()
        first = self.service.publish(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )

        with patch.object(
            self.service,
            "_set_status",
            wraps=self.service._set_status,
        ) as set_status_mock:
            second = self.service.publish(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )
            set_status_mock.assert_not_called()

        self.assertEqual(first.status, KnowledgeDocumentStatus.ACTIVE)
        self.assertEqual(second.status, KnowledgeDocumentStatus.ACTIVE)

    def test_publish_archived_raises(self) -> None:
        document = self._create_document()
        archived = self.service.archive(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertEqual(archived.status, KnowledgeDocumentStatus.ARCHIVED)

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            self.service.publish(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("cannot be published", ctx.exception.message.lower())

        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.ARCHIVED)

    def test_archive_draft_becomes_archived(self) -> None:
        document = self._create_document()

        archived = self.service.archive(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )

        self.assertEqual(archived.status, KnowledgeDocumentStatus.ARCHIVED)

    def test_archive_active_becomes_archived(self) -> None:
        document = self._create_document()
        self.service.publish(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )

        archived = self.service.archive(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )

        self.assertEqual(archived.status, KnowledgeDocumentStatus.ARCHIVED)

    def test_archive_archived_is_idempotent(self) -> None:
        document = self._create_document()
        first = self.service.archive(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )

        with patch.object(
            self.service,
            "_set_status",
            wraps=self.service._set_status,
        ) as set_status_mock:
            second = self.service.archive(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )
            set_status_mock.assert_not_called()

        self.assertEqual(first.status, KnowledgeDocumentStatus.ARCHIVED)
        self.assertEqual(second.status, KnowledgeDocumentStatus.ARCHIVED)

    def test_publish_unknown_document_raises(self) -> None:
        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            self.service.publish(
                self.db_path,
                company_id="company-a",
                document_id="missing-doc",
            )

        self.assertIn("not found", ctx.exception.message.lower())

    def test_archive_unknown_document_raises(self) -> None:
        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            self.service.archive(
                self.db_path,
                company_id="company-a",
                document_id="missing-doc",
            )

        self.assertIn("not found", ctx.exception.message.lower())

    def test_publish_other_company_document_raises(self) -> None:
        document = self._create_document(company_id="company-a")

        with self.assertRaises(KnowledgeDocumentLifecycleError):
            self.service.publish(
                self.db_path,
                company_id="company-b",
                document_id=document.document_id,
            )

        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.DRAFT)

    def test_archive_other_company_document_raises(self) -> None:
        document = self._create_document(company_id="company-a")

        with self.assertRaises(KnowledgeDocumentLifecycleError):
            self.service.archive(
                self.db_path,
                company_id="company-b",
                document_id=document.document_id,
            )

        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id="company-a",
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.DRAFT)

    def test_publish_set_status_false_raises(self) -> None:
        document = self._create_document()
        service = KnowledgeDocumentLifecycleService(set_status=lambda *args, **kwargs: False)

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            service.publish(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("failed to update", ctx.exception.message.lower())

    def test_archive_set_status_false_raises(self) -> None:
        document = self._create_document()
        service = KnowledgeDocumentLifecycleService(set_status=lambda *args, **kwargs: False)

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            service.archive(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("failed to update", ctx.exception.message.lower())

    def test_publish_reload_failure_raises(self) -> None:
        document = self._create_document()
        call_count = {"count": 0}

        def flaky_get_document(
            db_path: Path,
            *,
            company_id: str,
            document_id: str,
        ) -> Optional[KnowledgeDocument]:
            call_count["count"] += 1
            if call_count["count"] == 1:
                return knowledge_document_repository.get_by_document_id(
                    db_path,
                    company_id=company_id,
                    document_id=document_id,
                )
            return None

        service = KnowledgeDocumentLifecycleService(get_document=flaky_get_document)

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            service.publish(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("failed to update", ctx.exception.message.lower())

    def test_publish_reload_status_mismatch_raises(self) -> None:
        document = self._create_document()

        def get_document(
            db_path: Path,
            *,
            company_id: str,
            document_id: str,
        ) -> Optional[KnowledgeDocument]:
            return knowledge_document_repository.get_by_document_id(
                db_path,
                company_id=company_id,
                document_id=document_id,
            )

        service = KnowledgeDocumentLifecycleService(
            get_document=get_document,
            set_status=lambda *args, **kwargs: True,
        )

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            service.publish(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("failed to update", ctx.exception.message.lower())

        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.DRAFT)

    def test_archive_reload_status_mismatch_raises(self) -> None:
        document = self._create_document()

        def get_document(
            db_path: Path,
            *,
            company_id: str,
            document_id: str,
        ) -> Optional[KnowledgeDocument]:
            return knowledge_document_repository.get_by_document_id(
                db_path,
                company_id=company_id,
                document_id=document_id,
            )

        service = KnowledgeDocumentLifecycleService(
            get_document=get_document,
            set_status=lambda *args, **kwargs: True,
        )

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            service.archive(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("failed to update", ctx.exception.message.lower())

        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.DRAFT)

    def test_archive_active_reload_status_mismatch_raises(self) -> None:
        document = self._create_document()
        knowledge_document_repository.set_status(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        def get_document(
            db_path: Path,
            *,
            company_id: str,
            document_id: str,
        ) -> Optional[KnowledgeDocument]:
            return knowledge_document_repository.get_by_document_id(
                db_path,
                company_id=company_id,
                document_id=document_id,
            )

        service = KnowledgeDocumentLifecycleService(
            get_document=get_document,
            set_status=lambda *args, **kwargs: True,
        )

        with self.assertRaises(KnowledgeDocumentLifecycleError) as ctx:
            service.archive(
                self.db_path,
                company_id=document.company_id,
                document_id=document.document_id,
            )

        self.assertIn("failed to update", ctx.exception.message.lower())

        reloaded = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.status, KnowledgeDocumentStatus.ACTIVE)

    def test_empty_company_id_raises(self) -> None:
        document = self._create_document()

        with self.assertRaises(KnowledgeDocumentLifecycleError):
            self.service.publish(
                self.db_path,
                company_id="",
                document_id=document.document_id,
            )

    def test_empty_document_id_raises(self) -> None:
        with self.assertRaises(KnowledgeDocumentLifecycleError):
            self.service.publish(
                self.db_path,
                company_id="company-a",
                document_id="",
            )


class KnowledgeDocumentLifecycleRetrievalIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.lifecycle = KnowledgeDocumentLifecycleService()
        self.retrieval = KnowledgeChunkRetrievalService()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_searchable_document(self) -> KnowledgeDocument:
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id="company-a",
            title="Return Policy",
            original_filename="policy.pdf",
            source_type="pdf",
            extracted_text="Company return policy details.",
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text="Company return policy details.",
                    start_char=0,
                    end_char=31,
                )
            ],
        )
        return document

    def _search(self) -> tuple:
        return self.retrieval.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=5,
        )

    def test_draft_not_searchable_publish_makes_searchable_archive_hides_again(
        self,
    ) -> None:
        document = self._create_searchable_document()

        self.assertEqual(tuple(self._search()), ())

        published = self.lifecycle.publish(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertEqual(published.status, KnowledgeDocumentStatus.ACTIVE)
        self.assertEqual(len(self._search()), 1)

        archived = self.lifecycle.archive(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
        )
        self.assertEqual(archived.status, KnowledgeDocumentStatus.ARCHIVED)
        self.assertEqual(tuple(self._search()), ())


if __name__ == "__main__":
    unittest.main()
