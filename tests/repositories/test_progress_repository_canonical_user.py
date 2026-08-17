"""Tests for canonical-user progress repository access."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.progress_repository import ProgressRepository


class CanonicalUserProgressRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = ProgressRepository()

        with get_connection(self.db_path) as connection:
            self.user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name
                    )
                    VALUES (NULL, ?, ?, ?)
                    """,
                    ("web-only", "Web", "Learner"),
                ).lastrowid
            )

        course_repository = CourseRepository()
        lesson_repository = LessonRepository()

        course_id = course_repository.save(
            self.db_path,
            slug="alpha",
            title="Alpha",
            cover_path=None,
            sort_order=0,
        )

        for index, lesson_slug in enumerate(
            ("lesson_01", "lesson_02", "lesson_03")
        ):
            lesson_repository.save(
                self.db_path,
                course_id=course_id,
                slug=lesson_slug,
                title=lesson_slug,
                description="",
                image_path=None,
                narration_path=None,
                sort_order=index,
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_password_only_user_can_start_course(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.assertEqual(
            self.repository.get_course_progress_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            ),
            ("in_progress", 0),
        )

    def test_password_only_user_can_complete_lesson(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        self.repository.complete_lesson_for_user(
            self.db_path,
            self.user_id,
            "alpha",
            "lesson_01",
        )

        self.assertEqual(
            self.repository.get_resume_lesson_index_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            ),
            1,
        )
        self.assertEqual(
            self.repository.get_course_progress_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            ),
            ("in_progress", 33),
        )

    def test_complete_lesson_is_idempotent(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.repository.complete_lesson_for_user(
            self.db_path,
            self.user_id,
            "alpha",
            "lesson_01",
        )
        self.repository.complete_lesson_for_user(
            self.db_path,
            self.user_id,
            "alpha",
            "lesson_01",
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM lesson_progress
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_password_only_user_can_complete_course(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        for lesson_slug in ("lesson_01", "lesson_02", "lesson_03"):
            self.repository.complete_lesson_for_user(
                self.db_path,
                self.user_id,
                "alpha",
                lesson_slug,
            )

        self.repository.complete_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.assertEqual(
            self.repository.get_course_progress_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            ),
            ("completed", 100),
        )

    def test_latest_in_progress_course_works_without_telegram_id(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.assertEqual(
            self.repository.get_latest_in_progress_course_for_user(
                self.db_path,
                self.user_id,
            ),
            ("alpha", 0),
        )

    def test_unknown_user_does_not_create_enrollment(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            999999,
            "alpha",
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM enrollments"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_unknown_user_does_not_create_lesson_progress(self) -> None:
        self.repository.complete_lesson_for_user(
            self.db_path,
            999999,
            "alpha",
            "lesson_01",
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM lesson_progress"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_not_started_course_returns_default(self) -> None:
        self.assertEqual(
            self.repository.get_course_progress_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            ),
            ("not_started", 0),
        )

    def test_invalid_user_ids_are_rejected(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.repository.get_course_progress_for_user(
                        self.db_path,
                        invalid,  # type: ignore[arg-type]
                        "alpha",
                    )

    def test_canonical_progress_does_not_require_telegram_id(self) -> None:
        with get_connection(self.db_path) as connection:
            telegram_id = connection.execute(
                "SELECT telegram_id FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()["telegram_id"]

        self.assertIsNone(telegram_id)

        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        self.repository.complete_lesson_for_user(
            self.db_path,
            self.user_id,
            "alpha",
            "lesson_01",
        )

        self.assertEqual(
            self.repository.get_resume_lesson_index_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
