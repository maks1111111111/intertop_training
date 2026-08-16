"""Tests for Web lesson progress service."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from app.api.dto.course import LessonSummaryDTO
from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.progress_repository import ProgressRepository
from app.web.progress_service import WebProgressService

TELEGRAM_ID = 1001
OTHER_TELEGRAM_ID = 1002


def _seed_course(
    db_path: Path,
    slug: str,
    lesson_slugs: tuple[str, ...],
) -> None:
    course_repository = CourseRepository()
    lesson_repository = LessonRepository()
    course_id = course_repository.save(
        db_path,
        slug=slug,
        title=f"Title {slug}",
        cover_path=None,
        sort_order=0,
    )
    for index, lesson_slug in enumerate(lesson_slugs):
        lesson_repository.save(
            db_path,
            course_id=course_id,
            slug=lesson_slug,
            title=f"Lesson {lesson_slug}",
            description="",
            image_path=None,
            narration_path=None,
            sort_order=index,
        )


class WebProgressServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        upsert_telegram_user(
            self.db_path,
            telegram_id=TELEGRAM_ID,
            username="web-learner",
            first_name="Web",
            last_name="Learner",
        )
        _seed_course(
            self.db_path,
            "alpha",
            ("lesson_01", "lesson_02", "lesson_03"),
        )
        _seed_course(self.db_path, "beta", ("lesson_01",))
        self.progress_repository = ProgressRepository()
        self.service = WebProgressService(
            self.db_path,
            self.progress_repository,
            TELEGRAM_ID,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _lessons(self) -> tuple[LessonSummaryDTO, ...]:
        return (
            LessonSummaryDTO(id="lesson_01", title="First", order=1),
            LessonSummaryDTO(id="lesson_02", title="Second", order=2),
            LessonSummaryDTO(id="lesson_03", title="Third", order=3),
        )

    def test_runtime_does_not_reference_web_lesson_progress(self) -> None:
        source = inspect.getsource(WebProgressService)
        self.assertNotIn("web_lesson_progress", source)

    def test_invalid_telegram_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            WebProgressService(self.db_path, self.progress_repository, 0)
        with self.assertRaises(ValueError):
            WebProgressService(self.db_path, self.progress_repository, -1)
        with self.assertRaises(ValueError):
            WebProgressService(self.db_path, self.progress_repository, True)

    def test_unknown_user_has_zero_read_progress(self) -> None:
        unknown_service = WebProgressService(
            self.db_path,
            self.progress_repository,
            OTHER_TELEGRAM_ID,
        )
        self.assertFalse(unknown_service.is_lesson_completed("alpha", "lesson_01"))
        self.assertEqual(unknown_service.completed_lessons("alpha"), set())

    def test_unknown_user_does_not_create_progress_on_mark(self) -> None:
        unknown_service = WebProgressService(
            self.db_path,
            self.progress_repository,
            OTHER_TELEGRAM_ID,
        )
        unknown_service.mark_lesson_completed("alpha", "lesson_01")

        with get_connection(self.db_path) as connection:
            row_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM lesson_progress
                """
            ).fetchone()[0]
        self.assertEqual(row_count, 0)

    def test_mark_lesson_completed_writes_lesson_progress(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")
        self.assertTrue(self.service.is_lesson_completed("alpha", "lesson_01"))

        with get_connection(self.db_path) as connection:
            row_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM lesson_progress
                JOIN users ON users.id = lesson_progress.user_id
                JOIN lessons ON lessons.id = lesson_progress.lesson_id
                JOIN courses ON courses.id = lessons.course_id
                WHERE users.telegram_id = ?
                  AND courses.slug = ?
                  AND lessons.slug = ?
                """,
                (TELEGRAM_ID, "alpha", "lesson_01"),
            ).fetchone()[0]
            legacy_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM web_lesson_progress
                """
            ).fetchone()[0]
        self.assertEqual(row_count, 1)
        self.assertEqual(legacy_count, 0)

    def test_mark_lesson_completed_starts_enrollment(self) -> None:
        self.service.mark_lesson_completed("alpha", "lesson_01")

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT enrollments.status
                FROM enrollments
                JOIN users ON users.id = enrollments.user_id
                JOIN courses ON courses.id = enrollments.course_id
                WHERE users.telegram_id = ?
                  AND courses.slug = ?
                """,
                (TELEGRAM_ID, "alpha"),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "in_progress")

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
                FROM lesson_progress
                JOIN users ON users.id = lesson_progress.user_id
                JOIN lessons ON lessons.id = lesson_progress.lesson_id
                JOIN courses ON courses.id = lessons.course_id
                WHERE users.telegram_id = ?
                  AND courses.slug = ?
                  AND lessons.slug = ?
                """,
                (TELEGRAM_ID, "alpha", "lesson_01"),
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
        self.assertEqual(self.service.completed_lessons("alpha"), {"lesson_01"})
        self.assertEqual(self.service.completed_lessons("beta"), {"lesson_01"})

    def test_rows_are_isolated_by_user(self) -> None:
        upsert_telegram_user(
            self.db_path,
            telegram_id=OTHER_TELEGRAM_ID,
            username="other",
            first_name="Other",
            last_name="User",
        )
        other_service = WebProgressService(
            self.db_path,
            self.progress_repository,
            OTHER_TELEGRAM_ID,
        )
        self.service.mark_lesson_completed("alpha", "lesson_01")
        other_service.mark_lesson_completed("alpha", "lesson_02")

        self.assertEqual(self.service.completed_lessons("alpha"), {"lesson_01"})
        self.assertEqual(other_service.completed_lessons("alpha"), {"lesson_02"})


if __name__ == "__main__":
    unittest.main()
