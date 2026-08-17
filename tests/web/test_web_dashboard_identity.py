"""Tests for dashboard and progress identity wiring in the web router."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.database.db import get_connection
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.progress_repository import ProgressRepository
from app.web.router import get_web_company_id, get_web_identity_service
from app.web.web_identity_service import WebIdentity, WebIdentityService
from tests.web.test_web_ui import (
    _WEB_TEST_TELEGRAM_ID,
    _create_test_app,
    _write_multi_lesson_course,
)


def _seed_web_identity_context(db_path: Path, telegram_id: int = _WEB_TEST_TELEGRAM_ID) -> None:
    """Create the default intertop company membership for one web learner."""
    company_repository = CompanyRepository()
    membership_repository = CompanyMembershipRepository()
    company_repository.create(db_path, company_id="intertop", name="Intertop Retail")
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        ).fetchone()
    assert row is not None
    membership_repository.add(
        db_path,
        company_id="intertop",
        user_id=int(row["id"]),
        role="student",
    )


class WebDashboardIdentityRouterTests(unittest.TestCase):
    """Verify learner routes resolve identity through WebIdentityService."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)
        self.progress_repository = ProgressRepository()

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_dashboard_resolve_uses_web_identity_service(self) -> None:
        _seed_web_identity_context(self.db_path)
        fake_service = MagicMock(spec=WebIdentityService)
        fake_service.resolve.return_value = WebIdentity(
            user_id=10,
            telegram_id=_WEB_TEST_TELEGRAM_ID,
            company_id="intertop",
            company_name="Intertop Retail",
            role="student",
        )
        self.app.dependency_overrides[get_web_identity_service] = lambda: fake_service

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        fake_service.resolve.assert_called_once_with(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "intertop",
        )
        self.app.dependency_overrides.clear()

    def test_dashboard_uses_resolved_telegram_id_for_progress(self) -> None:
        _seed_web_identity_context(self.db_path)
        self.progress_repository.start_course(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "alpha",
        )
        self.progress_repository.complete_lesson(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "alpha",
            "lesson_01",
        )
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn("33%", response.text)
        self.assertIn("Последний урок: First lesson", response.text)

    def test_dashboard_falls_back_when_identity_unresolved(self) -> None:
        self.progress_repository.start_course(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "alpha",
        )
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("В процессе", response.text)

    def test_progress_service_uses_resolved_telegram_id(self) -> None:
        _seed_web_identity_context(self.db_path)
        self.progress_repository.start_course(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "alpha",
        )
        self.progress_repository.complete_lesson(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "alpha",
            "lesson_01",
        )
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("33%", response.text)
        self.assertIn("First lesson", response.text)

    def test_get_web_identity_service_returns_configured_service(self) -> None:
        service = get_web_identity_service()

        self.assertIsInstance(service, WebIdentityService)

    def test_web_company_id_uses_resolved_identity_tenant(self) -> None:
        fake_service = MagicMock(spec=WebIdentityService)
        fake_service.resolve.return_value = WebIdentity(
            user_id=10,
            telegram_id=_WEB_TEST_TELEGRAM_ID,
            company_id="company-b",
            company_name="Company B",
            role="admin",
        )

        company_id = get_web_company_id(self.db_path, fake_service)

        self.assertEqual(company_id, "company-b")
        fake_service.resolve.assert_called_once_with(
            self.db_path,
            _WEB_TEST_TELEGRAM_ID,
            "intertop",
        )

    def test_web_company_id_falls_back_until_web_authentication_exists(self) -> None:
        fake_service = MagicMock(spec=WebIdentityService)
        fake_service.resolve.return_value = None

        company_id = get_web_company_id(self.db_path, fake_service)

        self.assertEqual(company_id, "intertop")


class WebDashboardIdentityMembershipTests(unittest.TestCase):
    """Verify unresolved tenant membership does not break learner pages."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_dashboard_without_membership_still_renders_courses(self) -> None:
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha Course", response.text)
        self.assertIn("0%", response.text)

    def test_lesson_progress_without_membership_uses_fallback_user(self) -> None:
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        before = self.client.get("/courses/alpha/lessons/lesson_01")
        self.assertEqual(before.status_code, 200)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM lesson_progress
                JOIN users ON users.id = lesson_progress.user_id
                JOIN lessons ON lessons.id = lesson_progress.lesson_id
                JOIN courses ON courses.id = lessons.course_id
                WHERE users.telegram_id = ?
                  AND courses.slug = ?
                """,
                (_WEB_TEST_TELEGRAM_ID, "alpha"),
            ).fetchone()
        self.assertEqual(int(row[0]), 1)


if __name__ == "__main__":
    unittest.main()
