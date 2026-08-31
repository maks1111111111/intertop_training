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

        self.beta_course_id = course_repository.save(
            self.db_path,
            slug="beta",
            title="Beta",
            cover_path=None,
            sort_order=1,
        )

    def _enrollment_row(self, course_slug: str) -> dict:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    enrollments.status,
                    enrollments.progress_percent,
                    enrollments.assigned_at,
                    enrollments.assigned_by_user_id,
                    enrollments.started_at,
                    enrollments.completed_at
                FROM enrollments
                JOIN courses
                    ON courses.id = enrollments.course_id
                WHERE enrollments.user_id = ?
                  AND courses.slug = ?
                """,
                (self.user_id, course_slug),
            ).fetchone()

        self.assertIsNotNone(row)
        return dict(row)

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

    def test_assign_course_creates_assigned_enrollment(self) -> None:
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )

        enrollment = self._enrollment_row("alpha")
        self.assertEqual(enrollment["status"], "assigned")
        self.assertEqual(enrollment["progress_percent"], 0)
        self.assertIsNone(enrollment["started_at"])
        self.assertIsNone(enrollment["completed_at"])

        assigned = self.repository.get_assigned_courses_for_user(
            self.db_path,
            self.user_id,
        )
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0][0], "alpha")
        self.assertEqual(assigned[0][1], "Alpha")
        self.assertEqual(assigned[0][2], enrollment["assigned_at"])

    def test_manager_assignment_records_canonical_author(self) -> None:
        with get_connection(self.db_path) as connection:
            manager_user_id = int(
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
                    ("manager", "Manager", "User"),
                ).lastrowid
            )

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
                assigned_by_user_id=manager_user_id,
            )
        )

        enrollment = self._enrollment_row("alpha")
        self.assertEqual(
            enrollment["assigned_by_user_id"],
            manager_user_id,
        )

    def test_assignment_without_author_keeps_author_null(self) -> None:
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )

        enrollment = self._enrollment_row("alpha")
        self.assertIsNone(enrollment["assigned_by_user_id"])

    def test_repeated_assignment_does_not_replace_original_author(self) -> None:
        with get_connection(self.db_path) as connection:
            first_manager_id = int(
                connection.execute(
                    """
                    INSERT INTO users (username, first_name, last_name)
                    VALUES (?, ?, ?)
                    """,
                    ("manager-one", "Manager", "One"),
                ).lastrowid
            )
            second_manager_id = int(
                connection.execute(
                    """
                    INSERT INTO users (username, first_name, last_name)
                    VALUES (?, ?, ?)
                    """,
                    ("manager-two", "Manager", "Two"),
                ).lastrowid
            )

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
                assigned_by_user_id=first_manager_id,
            )
        )
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
                assigned_by_user_id=second_manager_id,
            )
        )

        enrollment = self._enrollment_row("alpha")
        self.assertEqual(
            enrollment["assigned_by_user_id"],
            first_manager_id,
        )

    def test_unknown_assignment_author_returns_false(self) -> None:
        self.assertFalse(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
                assigned_by_user_id=999999,
            )
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM enrollments
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_invalid_assignment_author_ids_are_rejected(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.repository.assign_course_to_user(
                        self.db_path,
                        self.user_id,
                        "alpha",
                        assigned_by_user_id=invalid,  # type: ignore[arg-type]
                    )

    def test_self_started_course_has_no_assignment_author(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        enrollment = self._enrollment_row("alpha")
        self.assertIsNone(enrollment["assigned_by_user_id"])

    def test_assign_course_unknown_user_returns_false(self) -> None:
        self.assertFalse(
            self.repository.assign_course_to_user(
                self.db_path,
                999999,
                "alpha",
            )
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM enrollments"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_assign_course_unknown_course_returns_false(self) -> None:
        self.assertFalse(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "missing-course",
            )
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM enrollments WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_repeated_assignment_is_idempotent(self) -> None:
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )
        first_assigned_at = self._enrollment_row("alpha")["assigned_at"]

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM enrollments
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()[0]

        enrollment = self._enrollment_row("alpha")
        self.assertEqual(count, 1)
        self.assertEqual(enrollment["status"], "assigned")
        self.assertEqual(enrollment["assigned_at"], first_assigned_at)

    def test_assign_does_not_downgrade_in_progress_course(self) -> None:
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
        before = self._enrollment_row("alpha")

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )

        after = self._enrollment_row("alpha")
        self.assertEqual(after["status"], "in_progress")
        self.assertEqual(after["progress_percent"], before["progress_percent"])
        self.assertEqual(after["started_at"], before["started_at"])

    def test_assigning_self_started_course_does_not_claim_manager_authorship(
        self,
    ) -> None:
        with get_connection(self.db_path) as connection:
            manager_user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (username, first_name, last_name)
                    VALUES (?, ?, ?)
                    """,
                    ("late-manager", "Late", "Manager"),
                ).lastrowid
            )

        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        before = self._enrollment_row("alpha")
        self.assertIsNone(before["assigned_by_user_id"])

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
                assigned_by_user_id=manager_user_id,
            )
        )

        after = self._enrollment_row("alpha")
        self.assertEqual(after["status"], "in_progress")
        self.assertEqual(after["started_at"], before["started_at"])
        self.assertEqual(after["assigned_at"], before["assigned_at"])
        self.assertIsNone(after["assigned_by_user_id"])

    def test_assign_does_not_downgrade_completed_course(self) -> None:
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        self.repository.complete_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        before = self._enrollment_row("alpha")

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )

        after = self._enrollment_row("alpha")
        self.assertEqual(after["status"], "completed")
        self.assertEqual(after["progress_percent"], before["progress_percent"])
        self.assertEqual(after["started_at"], before["started_at"])
        self.assertEqual(after["completed_at"], before["completed_at"])

    def test_assigning_completed_course_does_not_claim_manager_authorship(
        self,
    ) -> None:
        with get_connection(self.db_path) as connection:
            manager_user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (username, first_name, last_name)
                    VALUES (?, ?, ?)
                    """,
                    ("late-manager-completed", "Late", "Manager"),
                ).lastrowid
            )

        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        self.repository.complete_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        before = self._enrollment_row("alpha")
        self.assertIsNone(before["assigned_by_user_id"])

        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
                assigned_by_user_id=manager_user_id,
            )
        )

        after = self._enrollment_row("alpha")
        self.assertEqual(after["status"], "completed")
        self.assertEqual(after["completed_at"], before["completed_at"])
        self.assertEqual(after["assigned_at"], before["assigned_at"])
        self.assertIsNone(after["assigned_by_user_id"])

    def test_start_course_after_assignment_preserves_assigned_at(self) -> None:
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )
        assigned_at = self._enrollment_row("alpha")["assigned_at"]

        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        enrollment = self._enrollment_row("alpha")
        self.assertEqual(enrollment["status"], "in_progress")
        self.assertEqual(enrollment["assigned_at"], assigned_at)
        self.assertIsNotNone(enrollment["started_at"])
        self.assertEqual(
            self.repository.get_assigned_courses_for_user(
                self.db_path,
                self.user_id,
            ),
            [],
        )

    def test_get_assigned_courses_excludes_in_progress_and_completed(self) -> None:
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "beta",
            )
        )

        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "beta",
        )
        self.repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )
        self.repository.complete_course_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        assigned = self.repository.get_assigned_courses_for_user(
            self.db_path,
            self.user_id,
        )
        self.assertEqual(assigned, [])

    def test_assign_course_invalid_user_id_rejected(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.repository.assign_course_to_user(
                        self.db_path,
                        invalid,  # type: ignore[arg-type]
                        "alpha",
                    )

    def test_get_assigned_courses_invalid_user_id_rejected(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.repository.get_assigned_courses_for_user(
                        self.db_path,
                        invalid,  # type: ignore[arg-type]
                    )

    def test_password_only_user_can_be_assigned_course(self) -> None:
        with get_connection(self.db_path) as connection:
            telegram_id = connection.execute(
                "SELECT telegram_id FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()["telegram_id"]

        self.assertIsNone(telegram_id)
        self.assertTrue(
            self.repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
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
