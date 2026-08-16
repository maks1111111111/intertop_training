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
        response = self.client.get("/admin/courses/new/ai")
        self.assertEqual(response.status_code, 200)

    def test_create_page_contains_heading(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn("Создание курса", response.text)

    def test_create_page_displays_course_title_field(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn("Название курса", response.text)
        self.assertIn('id="course-title"', response.text)

    def test_create_page_displays_lesson_count_field(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn("Количество уроков", response.text)
        self.assertIn('id="lesson-count"', response.text)
        self.assertIn('type="number"', response.text)

    def test_create_page_has_source_language_selector(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn('id="source-language"', response.text)
        self.assertIn("Язык исходного документа", response.text)
        self.assertIn("Авто", response.text)
        self.assertIn("Русский", response.text)
        self.assertIn("Қазақша", response.text)
        self.assertIn("English", response.text)

    def test_create_page_has_output_language_selector(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn('id="output-language"', response.text)
        self.assertIn("Язык курса", response.text)
        output_section_start = response.text.index('id="output-language"')
        output_section = response.text[output_section_start : output_section_start + 500]
        self.assertNotIn('value="auto"', output_section)

    def test_create_page_has_difficulty_selector(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn('id="difficulty"', response.text)
        self.assertIn("Уровень сложности", response.text)
        self.assertIn("Начальный", response.text)
        self.assertIn("Базовый", response.text)
        self.assertIn("Продвинутый", response.text)
        self.assertIn("Экспертный", response.text)

    def test_create_page_has_lesson_size_selector(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn('id="lesson-size"', response.text)
        self.assertIn("Размер уроков", response.text)
        self.assertIn("Короткий", response.text)
        self.assertIn("Средний", response.text)
        self.assertIn("Длинный", response.text)

    def test_create_page_has_generation_checkboxes(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn('id="generate-quiz"', response.text)
        self.assertIn("Создать тест", response.text)
        self.assertIn('id="generate-practical-tasks"', response.text)
        self.assertIn("Практические задания", response.text)
        self.assertIn('id="generate-checklists"', response.text)
        self.assertIn("Чек-листы", response.text)
        self.assertIn('id="include-explanations"', response.text)
        self.assertIn("Пояснения", response.text)

    def test_create_page_has_continue_button(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn("Продолжить →", response.text)

    def test_create_page_does_not_render_accidental_english_labels(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        html = response.text
        accidental_labels = (
            "Course title",
            "Source Language",
            "Output Language",
            "Generation",
            "Lesson Count",
            "Lesson Size",
            "Difficulty",
            "Generate Quiz",
            "Generate Practical Tasks",
            "Generate Checklists",
            "Include Explanations",
            "Continue →",
            "Beginner",
            "Basic",
            "Advanced",
            "Expert",
            "Short",
            "Medium",
            "Long",
        )
        for label in accidental_labels:
            self.assertNotIn(label, html, f"Accidental English label found: {label!r}")

    def test_create_page_has_source_file_input(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertIn('name="source_file"', response.text)
        self.assertIn('enctype="multipart/form-data"', response.text)
        self.assertIn('method="post"', response.text)
        self.assertIn('action="/admin/courses/new/ai"', response.text)

    def test_create_page_back_button_points_to_admin(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
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
