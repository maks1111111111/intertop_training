"""HTTP tests for admin course delete routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import get_connection
from app.repositories.course_repository import CourseRepository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
)


def _management_identity(role: str = "admin") -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class AdminCourseDeletePageTests(unittest.TestCase):
    """Verify admin course delete confirmation and POST behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
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
        identity = _management_identity(role)
        self.app.dependency_overrides[get_current_web_identity] = lambda: identity

    def _sync_runtime(self) -> None:
        sync_courses(self.courses_dir, self.db_path)
        self.app.state.content_runtime.refresh()

    def _create_user(self) -> int:
        with get_connection(self.db_path) as connection:
            return int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name
                    )
                    VALUES (NULL, ?, ?, ?)
                    """,
                    ("web-only", "Web", "Learner"),
                ).lastrowid
            )

    def test_get_confirmation_for_unused_course(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha/delete")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Удаление курса", html)
        self.assertIn("Alpha Course", html)
        self.assertIn("Удалить навсегда", html)
        self.assertIn("необратимо", html.lower())

    def test_detail_page_links_to_delete_confirmation(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha")

        self.assertIn("Удалить курс", response.text)
        self.assertIn('href="/admin/courses/alpha/delete"', response.text)

    def test_used_course_shows_blocking_warning_without_submit(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()
        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )

        response = self.client.get("/admin/courses/alpha/delete")
        html = response.text

        self.assertIn(
            "Курс использовался в обучении и не может быть удалён без потери истории.",
            html,
        )
        self.assertNotIn("Удалить навсегда", html)

    def test_post_unused_course_redirects_to_admin(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.post("/admin/courses/alpha/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin")
        self.assertFalse((self.courses_dir / "alpha").exists())
        self.assertIsNone(CourseRepository().get_by_slug(self.db_path, "alpha"))
        self.app.state.content_runtime.refresh()
        self.assertIsNone(self.app.state.content_runtime.get_course("alpha"))

    def test_post_used_course_does_not_delete(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()
        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )

        response = self.client.post("/admin/courses/alpha/delete")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Курс использовался в обучении и не может быть удалён без потери истории.",
            response.text,
        )
        self.assertTrue((self.courses_dir / "alpha").exists())

    def test_unknown_slug_returns_404(self) -> None:
        self._set_identity("admin")

        response = self.client.get("/admin/courses/missing-course/delete")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_traversal_slug_cannot_delete(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/../alpha/delete")

        self.assertEqual(response.status_code, 404)
        self.assertTrue((self.courses_dir / "alpha").exists())

    def test_manager_can_delete_unused_course(self) -> None:
        self._set_identity("manager")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.post("/admin/courses/alpha/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)

    def test_student_cannot_access_delete_page(self) -> None:
        self._set_identity("student")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha/delete")

        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_access_delete_page(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha/delete")

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_post_delete(self) -> None:
        self._set_identity("student")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.post("/admin/courses/alpha/delete")

        self.assertEqual(response.status_code, 403)
        self.assertTrue((self.courses_dir / "alpha").exists())


if __name__ == "__main__":
    unittest.main()
