"""Tests for the admin course creation wizard generation options page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests.web.test_web_ui import _create_test_app


class AdminCourseCreatePageTests(unittest.TestCase):
    """Verify the course creation wizard generation options page."""

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

    def test_create_page_returns_200(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertEqual(response.status_code, 200)

    def test_create_page_contains_heading(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Создание курса", response.text)

    def test_create_page_displays_course_title_field(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Course title", response.text)
        self.assertIn('id="course-title"', response.text)

    def test_create_page_displays_lesson_count_field(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Lesson Count", response.text)
        self.assertIn('id="lesson-count"', response.text)
        self.assertIn('type="number"', response.text)

    def test_create_page_has_source_language_selector(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('id="source-language"', response.text)
        self.assertIn("Source Language", response.text)
        self.assertIn("Авто", response.text)
        self.assertIn("Русский", response.text)
        self.assertIn("Қазақша", response.text)
        self.assertIn("English", response.text)

    def test_create_page_has_output_language_selector(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('id="output-language"', response.text)
        self.assertIn("Output Language", response.text)
        output_section_start = response.text.index('id="output-language"')
        output_section = response.text[output_section_start : output_section_start + 500]
        self.assertNotIn('value="auto"', output_section)

    def test_create_page_has_difficulty_selector(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('id="difficulty"', response.text)
        self.assertIn("Difficulty", response.text)
        self.assertIn("Beginner", response.text)
        self.assertIn("Basic", response.text)
        self.assertIn("Advanced", response.text)
        self.assertIn("Expert", response.text)

    def test_create_page_has_lesson_size_selector(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('id="lesson-size"', response.text)
        self.assertIn("Lesson Size", response.text)
        self.assertIn("Short", response.text)
        self.assertIn("Medium", response.text)
        self.assertIn("Long", response.text)

    def test_create_page_has_generation_checkboxes(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('id="generate-quiz"', response.text)
        self.assertIn("Generate Quiz", response.text)
        self.assertIn('id="generate-practical-tasks"', response.text)
        self.assertIn("Generate Practical Tasks", response.text)
        self.assertIn('id="generate-checklists"', response.text)
        self.assertIn("Generate Checklists", response.text)
        self.assertIn('id="include-explanations"', response.text)
        self.assertIn("Include Explanations", response.text)

    def test_create_page_has_continue_button(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn("Continue →", response.text)

    def test_create_page_has_source_file_input(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('name="source_file"', response.text)
        self.assertIn('enctype="multipart/form-data"', response.text)
        self.assertIn('method="post"', response.text)
        self.assertIn('action="/admin/courses/new"', response.text)

    def test_create_page_back_button_points_to_admin(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertIn('href="/admin"', response.text)
        self.assertIn("Назад", response.text)

    def test_admin_dashboard_still_works(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Управление курсами", response.text)

    def test_admin_create_button_links_to_wizard(self) -> None:
        response = self.client.get("/admin")
        self.assertIn('href="/admin/courses/new"', response.text)


if __name__ == "__main__":
    unittest.main()
