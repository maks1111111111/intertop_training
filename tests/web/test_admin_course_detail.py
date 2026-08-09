"""Tests for the admin course detail Web page."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
    _write_multi_lesson_course,
)


def _write_course_with_quality_fields(
    courses_dir: Path,
    slug: str = "quality-course",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": "Quality Course",
                "description": "Course with quality lesson fields.",
                "status": "published",
                "language": "ru",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps(
            {
                "title": "Quality lesson",
                "order": 1,
                "description": "Lesson body.",
                "practical_task": "Do the task.",
                "checklist": ["Step one", "Step two"],
                "key_takeaways": ["Takeaway one"],
                "application_tips": ["Tip one"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class AdminCourseDetailPageTests(unittest.TestCase):
    """Verify the read-only admin course detail page."""

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

    def test_admin_detail_returns_200_for_existing_course(self) -> None:
        _write_course(
            self.courses_dir,
            "alpha",
            title="Alpha Course",
            description="Alpha description",
            language="ru",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")

        self.assertEqual(response.status_code, 200)

    def test_admin_detail_displays_course_metadata(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")
        html = response.text

        self.assertIn("Alpha Course", html)
        self.assertIn("ru", html)
        self.assertIn("3 уроков", html)
        self.assertIn("First lesson", html)
        self.assertIn("Second lesson", html)
        self.assertIn("Third lesson", html)

    def test_admin_detail_displays_description(self) -> None:
        _write_course(
            self.courses_dir,
            "alpha",
            title="Alpha Course",
            description="Alpha description",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")

        self.assertIn("Alpha description", response.text)

    def test_admin_detail_without_description_renders(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha Course", response.text)

    def test_admin_detail_with_quiz_displays_quiz_summary(self) -> None:
        _write_course_with_quiz(self.courses_dir, "quiz-course", passing_score=75)
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/quiz-course")
        html = response.text

        self.assertIn("Итоговый тест", html)
        self.assertIn("Создан", html)
        self.assertIn("2", html)
        self.assertIn("75%", html)

    def test_admin_detail_without_quiz_displays_no_quiz_state(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")
        html = response.text

        self.assertIn("Для этого курса итоговый тест не создан", html)

    def test_admin_detail_renders_lesson_quality_indicators(self) -> None:
        _write_course_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/quality-course")
        html = response.text

        self.assertIn("Практическое задание", html)
        self.assertIn("Чеклист", html)
        self.assertIn("Ключевые выводы", html)
        self.assertIn("Советы по применению", html)

    def test_admin_detail_missing_optional_fields_do_not_break(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Практическое задание", response.text)

    def test_unknown_slug_returns_404(self) -> None:
        response = self.client.get("/admin/courses/missing-course")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_no_filesystem_paths_in_html(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")
        html = response.text

        self.assertNotIn(str(self.courses_dir), html)

    def test_admin_dashboard_links_to_course_detail(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")

        self.assertIn('href="/admin/courses/alpha"', response.text)
        self.assertIn("Управление", response.text)

    def test_created_page_contains_manage_link(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha/created")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Управлять курсом", response.text)
        self.assertIn('href="/admin/courses/alpha"', response.text)

    def test_student_course_route_still_works(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha Course", response.text)

    def test_admin_dashboard_still_works(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Управление курсами", response.text)


if __name__ == "__main__":
    unittest.main()
