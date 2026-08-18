"""HTTP authentication contract for learner Web routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
)


def _identity(role: str = "student") -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class WebLearnerRouteSecurityTests(unittest.TestCase):
    """Verify learner Web pages require an authenticated Web identity."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()

        _write_course(
            self.courses_dir,
            "alpha",
            title="Alpha Course",
            language="ru",
        )

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

    def _set_identity(self, role: str = "student") -> None:
        identity = _identity(role)

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = identity
            return identity

        self.app.dependency_overrides[get_current_web_identity] = provide_identity

    def _assert_redirects_to_login(self, path: str) -> None:
        response = self.client.get(
            path,
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/login")

    def test_anonymous_root_redirects_to_login(self) -> None:
        response = self.client.get(
            "/",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login")

    def test_authenticated_root_redirects_to_dashboard(self) -> None:
        self._set_identity()

        response = self.client.get(
            "/",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/dashboard")

    def test_anonymous_dashboard_redirects_to_login(self) -> None:
        self._assert_redirects_to_login("/dashboard")

    def test_anonymous_courses_redirects_to_login(self) -> None:
        self._assert_redirects_to_login("/courses")

    def test_anonymous_course_detail_redirects_to_login(self) -> None:
        self._assert_redirects_to_login("/courses/alpha")

    def test_anonymous_lesson_redirects_to_login(self) -> None:
        self._assert_redirects_to_login(
            "/courses/alpha/lessons/lesson_01"
        )

    def test_student_can_open_dashboard(self) -> None:
        self._set_identity("student")

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)

    def test_student_can_open_courses(self) -> None:
        self._set_identity("student")

        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)

    def test_manager_can_open_learner_courses(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)

    def test_admin_can_open_learner_courses(self) -> None:
        self._set_identity("admin")

        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
