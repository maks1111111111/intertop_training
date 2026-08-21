"""HTTP tests for the tenant-scoped manager team page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.manager_team_service import ManagerTeamMember
from app.web.router import (
    get_current_web_identity,
    get_manager_team_service,
)
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app


class FakeManagerTeamService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_team(self, company_id: str) -> tuple[ManagerTeamMember, ...]:
        self.calls.append(company_id)
        return (
            ManagerTeamMember(
                user_id=2,
                display_name="E2E Student",
                username="web-e2e-student",
                role="student",
                role_label="Сотрудник",
                started_courses_count=1,
                completed_courses_count=0,
                average_progress_percent=100,
            ),
        )


def _identity(role: str) -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class ManagerTeamPageTests(unittest.TestCase):
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
        self.team_service = FakeManagerTeamService()
        self.app.dependency_overrides[get_manager_team_service] = lambda: self.team_service

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

    def test_manager_can_open_team_page(self) -> None:
        self._set_identity("manager")
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Команда", response.text)
        self.assertIn("E2E Student", response.text)
        self.assertIn("100%", response.text)
        self.assertEqual(self.team_service.calls, ["intertop"])

    def test_admin_can_open_team_page(self) -> None:
        self._set_identity("admin")
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 200)

    def test_student_cannot_open_team_page(self) -> None:
        self._set_identity("student")
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])

    def test_anonymous_cannot_open_team_page(self) -> None:
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])


if __name__ == "__main__":
    unittest.main()
