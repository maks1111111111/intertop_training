"""Tests for the admin dashboard Web page."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests.web.test_web_ui import _create_test_app, _write_course, _write_multi_lesson_course


class AdminDashboardPageTests(unittest.TestCase):
    """Verify the admin course management page."""

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

    def test_admin_page_returns_200(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)

    def test_admin_page_contains_heading(self) -> None:
        response = self.client.get("/admin")
        self.assertIn("Управление курсами", response.text)

    def test_admin_empty_state_renders(self) -> None:
        response = self.client.get("/admin")
        self.assertIn("Курсов пока нет", response.text)

    def test_admin_renders_runtime_course(self) -> None:
        _write_course(
            self.courses_dir,
            "alpha",
            title="Alpha Course",
            description="Alpha description",
            language="ru",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha Course", response.text)
        self.assertIn("Alpha description", response.text)
        self.assertIn("Язык: ru", response.text)
        self.assertIn("Опубликован", response.text)

    def test_admin_renders_lesson_count(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")
        self.assertIn("3 уроков", response.text)

    def test_admin_renders_course_link(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")
        self.assertIn('href="/courses/alpha"', response.text)
        self.assertIn('href="/admin/courses/alpha"', response.text)
        self.assertIn("Открыть курс", response.text)
        self.assertIn("Управление", response.text)

    def test_admin_renders_create_course_button(self) -> None:
        response = self.client.get("/admin")
        self.assertIn("Создать курс", response.text)
        self.assertIn('href="/admin/courses/new"', response.text)

    def test_admin_marks_nav_as_active(self) -> None:
        response = self.client.get("/admin")
        self.assertIn('href="/admin" class="nav-link is-active"', response.text)

    def test_courses_page_still_works(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/courses")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha Course", response.text)

    def test_dashboard_page_still_works(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Моё обучение", response.text)


    def test_admin_renders_archived_course_without_open_link(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        course_dir = self.courses_dir / "archived"
        course_dir.mkdir()
        (course_dir / "course.json").write_text(
            json.dumps(
                {
                    "title": "Archived Course",
                    "description": "Archived description",
                    "status": "archived",
                    "language": "ru",
                }
            ),
            encoding="utf-8",
        )
        lesson_dir = course_dir / "lesson_01"
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            '{"title": "First lesson", "order": 1, "description": "Body text."}',
            encoding="utf-8",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")
        html = response.text

        self.assertIn("Archived Course", html)
        self.assertIn("Архив", html)
        self.assertIn('admin-course-card--archived', html)
        self.assertIn('href="/courses/alpha"', html)
        self.assertNotIn('href="/courses/archived"', html)


if __name__ == "__main__":
    unittest.main()
