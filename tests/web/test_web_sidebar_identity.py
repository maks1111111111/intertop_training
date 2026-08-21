"""HTTP tests for identity-aware Web sidebar navigation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app


def _identity(role: str) -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class WebSidebarIdentityTests(unittest.TestCase):
    """Verify sidebar navigation follows the authenticated tenant role."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()

        (
            self.app,
            self.db_tmp,
            self.db_path,
            self.upload_tmp,
        ) = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _set_identity(self, role: str) -> None:
        identity = _identity(role)

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = identity
            return identity

        self.app.dependency_overrides[get_current_web_identity] = provide_identity

    def test_anonymous_courses_page_hides_account_navigation(self) -> None:
        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('class="sidebar-nav"', response.text)
        self.assertNotIn('action="/logout"', response.text)

    def test_student_sees_learning_navigation_without_admin(self) -> None:
        self._set_identity("student")

        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/courses"', response.text)
        self.assertIn('href="/dashboard"', response.text)
        self.assertNotIn('href="/admin"', response.text)
        self.assertNotIn('href="/manager/team"', response.text)
        self.assertIn("Intertop Retail", response.text)
        self.assertIn("Сотрудник", response.text)
        self.assertIn('action="/logout"', response.text)

    def test_manager_sees_admin_navigation(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/admin"', response.text)
        self.assertIn('href="/manager/team"', response.text)
        self.assertIn("Команда", response.text)
        self.assertIn("Менеджер", response.text)

    def test_admin_sees_admin_navigation(self) -> None:
        self._set_identity("admin")

        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/admin"', response.text)
        self.assertIn('href="/manager/team"', response.text)
        self.assertIn("Команда", response.text)
        self.assertIn("Администратор", response.text)


if __name__ == "__main__":
    unittest.main()
