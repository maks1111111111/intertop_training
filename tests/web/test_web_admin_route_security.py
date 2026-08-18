"""HTTP security contract for protected Web admin routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


class WebAdminRouteSecurityTests(unittest.TestCase):
    """Verify the admin router enforces management authorization over HTTP."""

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
        self.app.dependency_overrides[get_current_web_identity] = (
            lambda: identity
        )

    def test_anonymous_user_cannot_open_admin_dashboard(self) -> None:
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Forbidden")

    def test_student_cannot_open_admin_dashboard(self) -> None:
        self._set_identity("student")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Forbidden")

    def test_manager_can_open_admin_dashboard(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)

    def test_admin_can_open_admin_dashboard(self) -> None:
        self._set_identity("admin")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)

    def test_anonymous_user_cannot_open_nested_admin_route(self) -> None:
        response = self.client.get("/admin/courses/new")

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_open_nested_admin_route(self) -> None:
        self._set_identity("student")

        response = self.client.get("/admin/courses/new")

        self.assertEqual(response.status_code, 403)

    def test_manager_can_open_nested_admin_route(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/admin/courses/new")

        self.assertEqual(response.status_code, 200)

    def test_admin_can_open_nested_admin_route(self) -> None:
        self._set_identity("admin")

        response = self.client.get("/admin/courses/new")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
