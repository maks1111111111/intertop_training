"""Tests for the student dashboard Web page."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from tests.web.test_web_ui import _create_test_app


def _write_minimal_course(courses_dir: Path, slug: str) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "description": f"Description for {slug}",
                "status": "published",
                "order": 1,
            }
        ),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "First lesson", "order": 1}),
        encoding="utf-8",
    )


class DashboardPageTests(unittest.TestCase):
    """Verify GET /dashboard rendering and wiring."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path = _create_test_app(self.courses_dir)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_dashboard_returns_200(self) -> None:
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)

    def test_dashboard_contains_page_title(self) -> None:
        response = self.client.get("/dashboard")

        self.assertIn("Моё обучение", response.text)

    def test_dashboard_empty_state(self) -> None:
        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("Доступных курсов пока нет", html)

    def test_dashboard_renders_course_title(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn("Title alpha", response.text)

    def test_dashboard_renders_progress(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("0%", html)
        self.assertIn("dashboard-progress-bar", html)

    def test_dashboard_renders_continue_url(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn('href="/courses/alpha/lessons/lesson_01"', response.text)

    def test_dashboard_nav_link_is_active(self) -> None:
        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn('href="/dashboard"', html)
        self.assertIn("Моё обучение", html)
        self.assertIn("is-active", html)

    def test_dashboard_uses_app_state_runtime(self) -> None:
        _write_minimal_course(self.courses_dir, "beta")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn("Title beta", response.text)
        self.assertNotIn("Title alpha", response.text)


if __name__ == "__main__":
    unittest.main()
