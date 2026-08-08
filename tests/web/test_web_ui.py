"""Tests for the read-only Web Learning UI."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.content.runtime import ContentRuntime


def _write_course(
    courses_dir: Path,
    slug: str,
    *,
    title: str = "Sample Course",
    description: str = "Course overview for learners.",
    language: str = "ru",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        (
            '{"title": "'
            + title
            + '", "description": "'
            + description
            + '", "status": "published", "language": "'
            + language
            + '"}'
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        '{"title": "First lesson", "order": 1, "description": "Body text."}',
        encoding="utf-8",
    )


def _write_multi_lesson_course(courses_dir: Path, slug: str = "alpha") -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        '{"title": "Alpha Course", "status": "published", "language": "ru"}',
        encoding="utf-8",
    )
    for lesson_slug, title, order in (
        ("lesson_01", "First lesson", 1),
        ("lesson_02", "Second lesson", 2),
        ("lesson_03", "Third lesson", 3),
    ):
        lesson_dir = course_dir / lesson_slug
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            (
                '{"title": "'
                + title
                + '", "order": '
                + str(order)
                + ', "description": "Body text."}'
            ),
            encoding="utf-8",
        )


class WebUiTests(unittest.TestCase):
    """Verify server-rendered learning pages."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_course(self.courses_dir, "alpha", title="Alpha Course", language="ru")

        self.app = create_app()
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_root_redirects_to_courses(self) -> None:
        response = self.client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/courses")

    def test_courses_page_returns_200(self) -> None:
        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_courses_page_marks_courses_nav_as_active(self) -> None:
        response = self.client.get("/courses")
        html = response.text

        self.assertIn('href="/courses" class="nav-link is-active"', html)
        self.assertIn("sidebar-nav", html)
        self.assertIn("Курсы", html)

    def test_courses_page_shows_course_title_description_and_link(self) -> None:
        response = self.client.get("/courses")
        html = response.text

        self.assertIn("Alpha Course", html)
        self.assertIn("Course overview for learners.", html)
        self.assertIn('href="/courses/alpha"', html)
        self.assertIn("Открыть курс", html)

    def test_course_detail_page_returns_200(self) -> None:
        response = self.client.get("/courses/alpha")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Alpha Course", html)
        self.assertIn("Course overview for learners.", html)
        self.assertIn("First lesson", html)
        self.assertIn('href="/courses/alpha/lessons/lesson_01"', html)

    def test_lesson_page_returns_200_and_content(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_01")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("First lesson", html)
        self.assertIn("Body text.", html)

    def test_lesson_page_shows_quality_sections_when_present(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        lesson_path.write_text(
            json.dumps(
                {
                    "title": "First lesson",
                    "order": 1,
                    "description": "Body text.",
                    "practical_task": "Inspect the work area.",
                    "checklist": ["Wear PPE", "Check equipment"],
                    "common_mistakes": ["Skipping inspection"],
                    "key_takeaways": ["Safety first"],
                    "application_tips": ["Apply the checklist daily"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/courses/alpha/lessons/lesson_01")
        html = response.text

        self.assertIn("Практическое задание", html)
        self.assertIn("Inspect the work area.", html)
        self.assertIn("Чек-лист", html)
        self.assertIn("Wear PPE", html)
        self.assertIn("Типичные ошибки", html)
        self.assertIn("Skipping inspection", html)
        self.assertIn("Главное запомнить", html)
        self.assertIn("Safety first", html)
        self.assertIn("Советы по применению", html)
        self.assertIn("Apply the checklist daily", html)

    def test_lesson_page_hides_empty_quality_sections(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_01")
        html = response.text

        self.assertNotIn("Практическое задание", html)
        self.assertNotIn("Чек-лист", html)
        self.assertNotIn("Типичные ошибки", html)
        self.assertNotIn("Главное запомнить", html)
        self.assertNotIn("Советы по применению", html)

    def test_unknown_course_returns_html_404(self) -> None:
        response = self.client.get("/courses/missing")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Курс не найден", response.text)
        self.assertIn(
            "Запрошенный курс недоступен или не существует.",
            response.text,
        )
        self.assertNotIn('"course_not_found"', response.text)

    def test_unknown_lesson_returns_html_404(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_99")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Урок не найден", response.text)
        self.assertIn(
            "Запрошенный урок недоступен или не существует.",
            response.text,
        )
        self.assertNotIn('"lesson_not_found"', response.text)

    def test_api_courses_endpoint_still_works(self) -> None:
        response = self.client.get("/api/v1/courses")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["slug"], "alpha")

    def test_single_lesson_shows_complete_course_only(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_01")
        html = response.text

        self.assertNotIn("← Предыдущий урок", html)
        self.assertNotIn("Следующий урок →", html)
        self.assertIn("✓ Завершить курс", html)

    def test_lesson_navigation_for_multi_lesson_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_multi_lesson_course(courses_dir, "nav-course")
            app = create_app()
            app.state.content_runtime = ContentRuntime(courses_dir)
            client = TestClient(app)

            first = client.get("/courses/nav-course/lessons/lesson_01")
            middle = client.get("/courses/nav-course/lessons/lesson_02")
            last = client.get("/courses/nav-course/lessons/lesson_03")

        first_html = first.text
        middle_html = middle.text
        last_html = last.text

        self.assertNotIn("← Предыдущий урок", first_html)
        self.assertIn('href="/courses/nav-course/lessons/lesson_02"', first_html)
        self.assertIn("Следующий урок →", first_html)
        self.assertNotIn("✓ Завершить курс", first_html)

        self.assertIn('href="/courses/nav-course/lessons/lesson_01"', middle_html)
        self.assertIn("← Предыдущий урок", middle_html)
        self.assertIn('href="/courses/nav-course/lessons/lesson_03"', middle_html)
        self.assertIn("Следующий урок →", middle_html)
        self.assertNotIn("✓ Завершить курс", middle_html)

        self.assertIn('href="/courses/nav-course/lessons/lesson_02"', last_html)
        self.assertIn("← Предыдущий урок", last_html)
        self.assertNotIn("Следующий урок →", last_html)
        self.assertIn("✓ Завершить курс", last_html)


if __name__ == "__main__":
    unittest.main()
