"""Tests for admin Knowledge Base document lifecycle Web actions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.database.db import initialize_database
from app.knowledge.lifecycle_service import KnowledgeDocumentLifecycleError
from app.knowledge.models import KnowledgeDocumentStatus, KnowledgeSourceType
from app.repositories import knowledge_document_repository
from app.web.admin_knowledge_lifecycle_service import (
    AdminKnowledgeLifecycleError,
    AdminKnowledgeLifecycleService,
)
from tests.web.test_web_ui import _create_test_app


class AdminKnowledgeLifecycleServiceTests(unittest.TestCase):
    """Direct tests for AdminKnowledgeLifecycleService validation and mapping."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = AdminKnowledgeLifecycleService(self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_document(
        self,
        *,
        company_id: str = "intertop",
        title: str = "Policy",
        status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.DRAFT,
    ):
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename="policy.pdf",
            source_type=KnowledgeSourceType.PDF,
        )
        if status is not KnowledgeDocumentStatus.DRAFT:
            knowledge_document_repository.set_status(
                self.db_path,
                company_id=company_id,
                document_id=document.document_id,
                status=status,
            )
        return document

    def test_empty_company_id_rejected(self) -> None:
        document = self._create_document()

        with self.assertRaises(AdminKnowledgeLifecycleError) as ctx:
            self.service.publish("", document.document_id)

        self.assertEqual(ctx.exception.message, "Идентификатор компании обязателен.")

    def test_empty_document_id_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeLifecycleError) as ctx:
            self.service.publish("intertop", "   ")

        self.assertEqual(ctx.exception.message, "Идентификатор документа обязателен.")

    def test_traversal_document_id_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeLifecycleError) as ctx:
            self.service.publish("intertop", "../../secret")

        self.assertEqual(
            ctx.exception.message,
            "Недопустимый идентификатор документа.",
        )

    def test_lifecycle_error_mapped_to_russian(self) -> None:
        fake_lifecycle = Mock()
        fake_lifecycle.publish.side_effect = KnowledgeDocumentLifecycleError(
            "Archived knowledge documents cannot be published."
        )
        service = AdminKnowledgeLifecycleService(
            self.db_path,
            lifecycle_service=fake_lifecycle,
        )

        with self.assertRaises(AdminKnowledgeLifecycleError) as ctx:
            service.publish("intertop", "doc-id")

        self.assertEqual(
            ctx.exception.message,
            "Архивные документы нельзя опубликовать.",
        )

    def test_unknown_lifecycle_error_message_not_exposed_on_publish(self) -> None:
        fake_lifecycle = Mock()
        fake_lifecycle.publish.side_effect = KnowledgeDocumentLifecycleError(
            "sqlite path /secret/db.sqlite exploded"
        )
        service = AdminKnowledgeLifecycleService(
            self.db_path,
            lifecycle_service=fake_lifecycle,
        )

        with self.assertRaises(AdminKnowledgeLifecycleError) as ctx:
            service.publish("intertop", "doc-id")

        self.assertEqual(
            ctx.exception.message,
            "Не удалось изменить статус документа.",
        )
        self.assertNotIn("/secret/db.sqlite", ctx.exception.message)

    def test_unknown_lifecycle_error_message_not_exposed_on_archive(self) -> None:
        fake_lifecycle = Mock()
        fake_lifecycle.archive.side_effect = KnowledgeDocumentLifecycleError(
            "sqlite path /secret/db.sqlite exploded"
        )
        service = AdminKnowledgeLifecycleService(
            self.db_path,
            lifecycle_service=fake_lifecycle,
        )

        with self.assertRaises(AdminKnowledgeLifecycleError) as ctx:
            service.archive("intertop", "doc-id")

        self.assertEqual(
            ctx.exception.message,
            "Не удалось изменить статус документа.",
        )
        self.assertNotIn("/secret/db.sqlite", ctx.exception.message)

    def test_publish_delegates_to_lifecycle_service(self) -> None:
        document = self._create_document()

        published = self.service.publish("intertop", document.document_id)

        self.assertEqual(published.status, KnowledgeDocumentStatus.ACTIVE)


class AdminKnowledgeLifecycleRouteTests(unittest.TestCase):
    """HTTP tests for Knowledge Base publish/archive routes."""

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
        status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.DRAFT,
    ):
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename="manual.pdf",
            source_type=KnowledgeSourceType.PDF,
        )
        if status is not KnowledgeDocumentStatus.DRAFT:
            knowledge_document_repository.set_status(
                self.db_path,
                company_id=company_id,
                document_id=document.document_id,
                status=status,
            )
        return document

    def _get_status(
        self,
        *,
        company_id: str,
        document_id: str,
    ) -> KnowledgeDocumentStatus:
        document = knowledge_document_repository.get_by_document_id(
            self.db_path,
            company_id=company_id,
            document_id=document_id,
        )
        self.assertIsNotNone(document)
        assert document is not None
        return document.status

    def test_publish_route_changes_draft_to_active(self) -> None:
        document = self._create_document(title="Draft Doc")

        response = self.client.post(
            f"/admin/knowledge/{document.document_id}/publish",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self._get_status(
                company_id=document.company_id,
                document_id=document.document_id,
            ),
            KnowledgeDocumentStatus.ACTIVE,
        )

    def test_publish_route_redirects_to_knowledge_page(self) -> None:
        document = self._create_document()

        response = self.client.post(
            f"/admin/knowledge/{document.document_id}/publish",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/knowledge")

    def test_archive_route_changes_draft_to_archived(self) -> None:
        document = self._create_document(title="Draft To Archive")

        response = self.client.post(
            f"/admin/knowledge/{document.document_id}/archive",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self._get_status(
                company_id=document.company_id,
                document_id=document.document_id,
            ),
            KnowledgeDocumentStatus.ARCHIVED,
        )

    def test_archive_route_changes_active_to_archived(self) -> None:
        document = self._create_document(
            title="Active To Archive",
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        response = self.client.post(
            f"/admin/knowledge/{document.document_id}/archive",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self._get_status(
                company_id=document.company_id,
                document_id=document.document_id,
            ),
            KnowledgeDocumentStatus.ARCHIVED,
        )

    def test_archived_document_cannot_be_published(self) -> None:
        document = self._create_document(
            title="Archived Doc",
            status=KnowledgeDocumentStatus.ARCHIVED,
        )

        response = self.client.post(
            f"/admin/knowledge/{document.document_id}/publish"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Архивные документы нельзя опубликовать.", response.text)
        self.assertEqual(
            self._get_status(
                company_id=document.company_id,
                document_id=document.document_id,
            ),
            KnowledgeDocumentStatus.ARCHIVED,
        )

    def test_unknown_document_shows_safe_error(self) -> None:
        response = self.client.post(
            "/admin/knowledge/nonexistent-document-id/publish"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Документ не найден.", response.text)

    def test_other_company_document_cannot_be_changed(self) -> None:
        document = self._create_document(
            company_id="other-company",
            title="Hidden Doc",
        )

        response = self.client.post(
            f"/admin/knowledge/{document.document_id}/publish"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Документ не найден.", response.text)
        self.assertNotIn("Hidden Doc", response.text)
        self.assertEqual(
            self._get_status(
                company_id=document.company_id,
                document_id=document.document_id,
            ),
            KnowledgeDocumentStatus.DRAFT,
        )

    def test_draft_document_shows_publish_and_archive_forms(self) -> None:
        document = self._create_document(title="Draft With Actions")

        response = self.client.get("/admin/knowledge")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'action="/admin/knowledge/{document.document_id}/publish"',
            response.text,
        )
        self.assertIn(
            f'action="/admin/knowledge/{document.document_id}/archive"',
            response.text,
        )
        self.assertIn("Опубликовать", response.text)
        self.assertIn("В архив", response.text)

    def test_active_document_shows_archive_form_only(self) -> None:
        document = self._create_document(
            title="Active With Actions",
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        response = self.client.get("/admin/knowledge")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            f'action="/admin/knowledge/{document.document_id}/publish"',
            response.text,
        )
        self.assertIn(
            f'action="/admin/knowledge/{document.document_id}/archive"',
            response.text,
        )

    def test_archived_document_has_no_lifecycle_actions(self) -> None:
        document = self._create_document(
            title="Archived Without Actions",
            status=KnowledgeDocumentStatus.ARCHIVED,
        )

        response = self.client.get("/admin/knowledge")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Archived Without Actions", response.text)
        self.assertNotIn(
            f'action="/admin/knowledge/{document.document_id}/publish"',
            response.text,
        )
        self.assertNotIn(
            f'action="/admin/knowledge/{document.document_id}/archive"',
            response.text,
        )

    def test_routes_use_centralized_company_identity(self) -> None:
        document = self._create_document(company_id="intertop")
        other = self._create_document(company_id="other-company", title="Other")

        with patch(
            "app.web.router._WEB_ADMIN_COMPANY_ID",
            "intertop",
        ):
            response = self.client.post(
                f"/admin/knowledge/{document.document_id}/publish",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self._get_status(
                company_id="intertop",
                document_id=document.document_id,
            ),
            KnowledgeDocumentStatus.ACTIVE,
        )
        self.assertEqual(
            self._get_status(
                company_id="other-company",
                document_id=other.document_id,
            ),
            KnowledgeDocumentStatus.DRAFT,
        )

    def test_knowledge_page_still_works_after_lifecycle_error(self) -> None:
        self._create_document(title="Visible Doc")

        response = self.client.post(
            "/admin/knowledge/missing-id/publish"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Visible Doc", response.text)
        self.assertNotIn("Документы базы знаний пока отсутствуют.", response.text)


if __name__ == "__main__":
    unittest.main()
