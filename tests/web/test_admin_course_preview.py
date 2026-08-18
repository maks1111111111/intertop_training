"""Tests for admin course preview mode."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import get_connection
from app.repositories.progress_repository import ProgressRepository
from app.web.progress_service import WebProgressService
from tests.web.test_web_ui import _authenticate_test_web_user
from tests.web.test_web_ui import (
    _WEB_TEST_TELEGRAM_ID,
    _create_test_app,
    _write_course_with_quiz,
    _write_multi_lesson_course,
)


def _canonical_progress_row_count(db_path: Path, course_slug: str) -> int:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM lesson_progress
            JOIN users ON users.id = lesson_progress.user_id
            JOIN lessons ON lessons.id = lesson_progress.lesson_id
            JOIN courses ON courses.id = lessons.course_id
            WHERE users.telegram_id = ?
              AND courses.slug = ?
            """,
            (_WEB_TEST_TELEGRAM_ID, course_slug),
        ).fetchone()
    return int(row[0])


class AdminCoursePreviewTests(unittest.TestCase):
    """Verify isolated admin preview mode for courses, lessons, and quizzes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_multi_lesson_course(self.courses_dir, "preview-course")
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)
        self.progress = WebProgressService(
            self.db_path,
            ProgressRepository(),
            _WEB_TEST_TELEGRAM_ID,
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_preview_course_page_returns_200(self) -> None:
        response = self.client.get("/admin/courses/preview-course/preview")

        self.assertEqual(response.status_code, 200)
        self.assertIn("preview-banner", response.text)
        self.assertIn("Режим предпросмотра", response.text)
        self.assertIn("Вернуться в админку", response.text)

    def test_preview_course_shows_start_preview_action(self) -> None:
        response = self.client.get("/admin/courses/preview-course/preview")

        self.assertIn("Начать предпросмотр", response.text)
        self.assertIn(
            'href="/admin/courses/preview-course/preview/lessons/lesson_01"',
            response.text,
        )

    def test_preview_lesson_page_returns_200(self) -> None:
        response = self.client.get(
            "/admin/courses/preview-course/preview/lessons/lesson_01"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("First lesson", response.text)
        self.assertIn("Режим предпросмотра", response.text)

    def test_preview_lesson_does_not_record_progress(self) -> None:
        self.client.get("/admin/courses/preview-course/preview/lessons/lesson_01")

        self.assertEqual(_canonical_progress_row_count(self.db_path, "preview-course"), 0)
        self.assertFalse(
            self.progress.is_lesson_completed("preview-course", "lesson_01")
        )

    def test_preview_navigation_between_lessons(self) -> None:
        response = self.client.get(
            "/admin/courses/preview-course/preview/lessons/lesson_01"
        )
        html = response.text

        self.assertIn(
            'href="/admin/courses/preview-course/preview/lessons/lesson_02"',
            html,
        )

    def test_preview_last_lesson_links_to_quiz_when_quiz_missing(self) -> None:
        response = self.client.get(
            "/admin/courses/preview-course/preview/lessons/lesson_03"
        )

        self.assertNotIn("Перейти к итоговому тесту", response.text)
        self.assertNotIn("✓ Завершить курс", response.text)

    def test_admin_detail_links_to_preview_routes(self) -> None:
        response = self.client.get("/admin/courses/preview-course")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'href="/admin/courses/preview-course/preview"',
            response.text,
        )
        self.assertIn(
            'href="/admin/courses/preview-course/preview/lessons/lesson_01"',
            response.text,
        )

    def test_unknown_preview_course_returns_404(self) -> None:
        response = self.client.get("/admin/courses/missing/preview")

        self.assertEqual(response.status_code, 404)


class AdminCoursePreviewQuizTests(unittest.TestCase):
    """Verify quiz preview flow without persistence."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_course_with_quiz(self.courses_dir, "quiz-preview")
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_preview_last_lesson_links_to_quiz(self) -> None:
        response = self.client.get(
            "/admin/courses/quiz-preview/preview/lessons/lesson_01"
        )

        self.assertIn("Перейти к итоговому тесту", response.text)
        self.assertIn(
            'href="/admin/courses/quiz-preview/preview/quiz"',
            response.text,
        )

    def test_preview_quiz_page_returns_200(self) -> None:
        response = self.client.get("/admin/courses/quiz-preview/preview/quiz")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Итоговый тест", response.text)
        self.assertIn("Режим предпросмотра", response.text)
        self.assertIn('action="/admin/courses/quiz-preview/preview/quiz"', response.text)

    def test_preview_quiz_submit_shows_preview_result(self) -> None:
        response = self.client.post(
            "/admin/courses/quiz-preview/preview/quiz",
            data={"answer_q1": "b", "answer_q2": "d"},
        )

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Предпросмотр результата", html)
        self.assertIn("Результаты не сохранены", html)
        self.assertIn("100%", html)
        self.assertIn("Тест считается пройденным", html)
        self.assertIn('href="/admin/courses/quiz-preview"', html)
        self.assertIn('href="/admin/courses/quiz-preview/edit"', html)

    def test_admin_detail_shows_quiz_preview_link(self) -> None:
        response = self.client.get("/admin/courses/quiz-preview")

        self.assertIn(
            'href="/admin/courses/quiz-preview/preview/quiz"',
            response.text,
        )
        self.assertIn("Предпросмотр теста", response.text)

    def test_student_routes_still_work(self) -> None:
        _authenticate_test_web_user(self.client.app)
        response = self.client.get("/courses/quiz-preview")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Режим предпросмотра", response.text)


if __name__ == "__main__":
    unittest.main()