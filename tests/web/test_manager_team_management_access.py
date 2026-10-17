"""Browser access behaviour for the team-management workspace."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.database.db import get_connection
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app


def _identity(role: str, *, user_id: int = 10) -> WebIdentity:
    return WebIdentity(
        user_id=user_id,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class ManagerTeamManagementAccessTests(unittest.TestCase):
    """Keep management GET UX separate from unsafe-route authorization."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        courses_dir = Path(self._tmpdir.name) / "courses"
        courses_dir.mkdir()
        self.app, self._db_tmp, self._db_path, self._upload_tmp = _create_test_app(
            courses_dir,
            management_identity=False,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self._upload_tmp.cleanup()
        self._db_tmp.cleanup()
        self._tmpdir.cleanup()

    def _set_identity(self, role: str) -> None:
        user_id = 10
        if role == "admin":
            CompanyRepository().create(
                self._db_path,
                company_id="intertop",
                name="Intertop Retail",
            )
            with get_connection(self._db_path) as connection:
                row = connection.execute(
                    "SELECT id FROM users WHERE telegram_id = 1"
                ).fetchone()
            assert row is not None
            user_id = int(row["id"])
            CompanyMembershipRepository().add(
                self._db_path,
                company_id="intertop",
                user_id=user_id,
                role="admin",
            )
        identity = _identity(role, user_id=user_id)

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = identity
            return identity

        self.app.dependency_overrides[get_current_web_identity] = provide_identity

    def test_manager_can_open_management_page(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/manage")

        self.assertEqual(response.status_code, 200)

    def test_admin_can_open_management_page(self) -> None:
        self._set_identity("admin")

        response = self.client.get("/manager/team/manage")

        self.assertEqual(response.status_code, 200)

    def test_student_gets_html_forbidden_page_not_raw_json(self) -> None:
        self._set_identity("student")

        response = self.client.get("/manager/team/manage")

        self.assertEqual(response.status_code, 403)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Доступ ограничен", response.text)
        self.assertNotIn('{"detail":"Forbidden"}', response.text)

    def test_unresolved_identity_is_redirected_to_login(self) -> None:
        response = self.client.get(
            "/manager/team/manage",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_unresolved_management_post_remains_forbidden_json(self) -> None:
        response = self.client.post(
            "/manager/team/departments",
            data={"name": "Operations"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Forbidden"})

    def test_api_http_exception_behavior_remains_json(self) -> None:
        response = self.client.get("/api/v1/courses")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required"})


if __name__ == "__main__":
    unittest.main()
