"""Tests for the admin course creation wizard foundation page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests.web.test_web_ui import _create_test_app, _write_course


class AdminCourseCreatePageTests(unittest.TestCase):
    """Verify the course creation wizard foundation page."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path = _create_test_app(self.courses_dir)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_create_page_returns_200(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertEqual(response.status_code, 200)

    def test_create_page_contains_heading(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Создание курса", response.text)

    def test_create_page_has_language_selector(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('id="course-language"', response.text)
        self.assertIn("Авто", response.text)
        self.assertIn("Русский", response.text)
        self.assertIn("Қазақша", response.text)
        self.assertIn("English", response.text)

    def test_create_page_has_continue_button(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Продолжить", response.text)

    def test_create_page_back_button_points_to_admin(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('href="/admin"', response.text)
        self.assertIn("Назад", response.text)

    def test_create_page_has_form_fields(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Название курса", response.text)
        self.assertIn("Описание курса", response.text)
        self.assertIn('id="course-title"', response.text)
        self.assertIn('id="course-description"', response.text)

    def test_admin_dashboard_still_works(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Управление курсами", response.text)

    def test_admin_create_button_links_to_wizard(self) -> None:
        response = self.client.get("/admin")
        self.assertIn('href="/admin/courses/new"', response.text)


if __name__ == "__main__":
    unittest.main()
