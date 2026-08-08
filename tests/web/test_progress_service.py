"""Tests for Web lesson progress service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.api.dto.course import LessonSummaryDTO
from app.database.db import get_connection, initialize_database
from app.web.progress_service import WebProgressService


class WebProgressServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = WebProgressService(self.db_path, user_id="test-web-user")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _lessons(self) -> tuple[LessonSummaryDTO, ...]:
        return (
            LessonSummaryDTO(id="lesson_01", title="First", order=1),
            LessonSummaryDTO(id="lesson_02", title="Second", order=2),
            LessonSummaryDTO(id="lesson_03", title="Third", order=3),
        )

    def test_mark_lesson_completed_creates_row(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.assertTrue(self.service.is_lesson_completed("alpha", "lesson_01"))

    def test_mark_lesson_completed_is_idempotent(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.assertEqual(
            self.service.completed_lessons("alpha"),
            {"lesson_01"},
        )
        with get_connection(self.db_path) as connection:
            row_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM web_lesson_progress
                WHERE user_id = ? AND course_slug = ? AND lesson_id = ?
                """,
                ("test-web-user", "alpha", "lesson_01"),
            ).fetchone()[0]
        self.assertEqual(row_count, 1)

    def test_completed_lessons_returns_lesson_ids(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_02")
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.assertEqual(
            self.service.completed_lessons("alpha"),
            {"lesson_01", "lesson_02"},
        )

    def test_course_progress_percent(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        lesson_ids = tuple(lesson.id for lesson in self._lessons())
        percent = self.service.course_progress_percent("alpha", lesson_ids)
        self.assertEqual(percent, 33)

    def test_course_progress_percent_for_zero_lessons(self) -> None:
        self.assertEqual(
            self.service.course_progress_percent("alpha", ()),
            0,
        )

    def test_course_completed(self) -> None:
        lesson_ids = tuple(lesson.id for lesson in self._lessons())
        for lesson_id in lesson_ids:
            self.service.mark_lesson_completed("alpha", lesson_id)
        self.assertTrue(self.service.course_completed("alpha", lesson_ids))

    def test_course_not_completed_with_zero_lessons(self) -> None:
        self.assertFalse(self.service.course_completed("alpha", ()))

    def test_stale_lesson_ids_do_not_inflate_progress(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.service.mark_lesson_completed("alpha", "stale_lesson")
        lessons = self._lessons()
        lesson_ids = tuple(lesson.id for lesson in lessons)

        self.assertEqual(
            self.service._completed_count_for_lessons("alpha", lesson_ids),
            1,
        )
        self.assertEqual(self.service.course_progress_percent("alpha", lesson_ids), 33)
        self.assertFalse(self.service.course_completed("alpha", lesson_ids))

        view = self.service.build_course_progress_view(
            "alpha",
            lessons,
            has_quiz=False,
        )
        self.assertEqual(view.completed_count, 1)
        self.assertEqual(view.percent, 33)
        self.assertFalse(view.is_completed)

    def test_build_course_progress_view_marks_current_lesson(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        view = self.service.build_course_progress_view(
            "alpha",
            self._lessons(),
            has_quiz=False,
        )
        self.assertEqual(view.percent, 33)
        self.assertEqual(view.completed_count, 1)
        self.assertEqual(view.total_count, 3)
        self.assertFalse(view.is_completed)
        self.assertIsNone(view.completion_message)
        self.assertEqual(view.lesson_rows[0].status, "completed")
        self.assertEqual(view.lesson_rows[1].status, "current")
        self.assertEqual(view.lesson_rows[2].status, "not_started")

    def test_build_course_progress_view_completion_without_quiz(self) -> None:
        for lesson_id in ("lesson_01", "lesson_02", "lesson_03"):
            self.service.mark_lesson_completed("alpha", lesson_id)
        view = self.service.build_course_progress_view(
            "alpha",
            self._lessons(),
            has_quiz=False,
        )
        self.assertTrue(view.is_completed)
        self.assertEqual(view.completion_message, "Курс завершён")

    def test_build_course_progress_view_completion_with_quiz(self) -> None:
        for lesson_id in ("lesson_01", "lesson_02", "lesson_03"):
            self.service.mark_lesson_completed("alpha", lesson_id)
        view = self.service.build_course_progress_view(
            "alpha",
            self._lessons(),
            has_quiz=True,
        )
        self.assertEqual(view.completion_message, "Можно пройти итоговый тест")

    def test_build_course_progress_view_single_lesson(self) -> None:
        lessons = (LessonSummaryDTO(id="lesson_01", title="Only", order=1),)
        view = self.service.build_course_progress_view(
            "alpha",
            lessons,
            has_quiz=False,
        )
        self.assertEqual(view.lesson_rows[0].status, "current")
        self.assertEqual(view.lesson_rows[0].status_label, "Текущий")

    def test_rows_are_isolated_by_course(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.service.mark_lesson_completed("beta", "lesson_01")
        with get_connection(self.db_path) as connection:
            alpha_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM web_lesson_progress
                WHERE user_id = ? AND course_slug = ?
                """,
                ("test-web-user", "alpha"),
            ).fetchone()[0]
            beta_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM web_lesson_progress
                WHERE user_id = ? AND course_slug = ?
                """,
                ("test-web-user", "beta"),
            ).fetchone()[0]
        self.assertEqual(alpha_count, 1)
        self.assertEqual(beta_count, 1)


if __name__ == "__main__":
    unittest.main()
