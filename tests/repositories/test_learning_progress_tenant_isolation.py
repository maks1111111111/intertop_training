"""Cross-tenant regression tests for persisted learning results."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories import practical_task_attempt_repository, quiz_repository
from app.repositories.company_team_repository import CompanyTeamRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.progress_repository import ProgressRepository


class LearningProgressTenantIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "tenant-learning.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            connection.executemany(
                "INSERT INTO companies (id, name) VALUES (?, ?)",
                (("company-a", "Company A"), ("company-b", "Company B")),
            )
        upsert_telegram_user(
            self.db_path, 101, "shared", "Shared", "Learner"
        )
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = 101"
            ).fetchone()
        assert row is not None
        self.user_id = int(row["id"])
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO company_memberships (company_id, user_id, role)
                VALUES ('company-a', ?, 'student')
                """,
                (self.user_id,),
            )
        course_id = CourseRepository().save(
            self.db_path, "safety", "Safety", None, 0, "company-a"
        )
        LessonRepository().save(
            self.db_path,
            course_id,
            "lesson-1",
            "Lesson",
            "",
            None,
            None,
            0,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_progress_is_separate_for_the_same_user_and_course(self) -> None:
        repository = ProgressRepository()
        repository.start_course_for_user(
            self.db_path, self.user_id, "safety", "company-a"
        )
        repository.complete_lesson_for_user(
            self.db_path, self.user_id, "safety", "lesson-1", "company-a"
        )

        self.assertEqual(
            repository.get_course_progress_for_user(
                self.db_path, self.user_id, "safety", "company-a"
            ),
            ("in_progress", 100),
        )
        self.assertEqual(
            repository.get_course_progress_for_user(
                self.db_path, self.user_id, "safety", "company-b"
            ),
            ("not_started", 0),
        )
        self.assertEqual(
            repository.get_resume_lesson_index_for_user(
                self.db_path, self.user_id, "safety", "company-b"
            ),
            0,
        )

    def test_latest_course_ignores_legacy_cross_tenant_enrollment(self) -> None:
        """Read paths stay isolated even if historical data violates the new invariant."""
        other_course_id = CourseRepository().save(
            self.db_path, "other-safety", "Other Safety", None, 0, "company-b"
        )
        with get_connection(self.db_path) as connection:
            connection.execute(
                "DROP TRIGGER enforce_enrollment_course_company_insert"
            )
            connection.execute(
                """
                INSERT INTO enrollments (
                    company_id, user_id, course_id, status, progress_percent
                )
                VALUES ('company-a', ?, ?, 'in_progress', 75)
                """,
                (self.user_id, other_course_id),
            )

        self.assertIsNone(
            ProgressRepository().get_latest_in_progress_course_for_user(
                self.db_path, self.user_id, "company-a"
            )
        )

    def test_team_summary_ignores_legacy_cross_tenant_enrollment(self) -> None:
        other_course_id = CourseRepository().save(
            self.db_path, "other-safety", "Other Safety", None, 0, "company-b"
        )
        with get_connection(self.db_path) as connection:
            connection.execute(
                "DROP TRIGGER enforce_enrollment_course_company_insert"
            )
            connection.execute(
                """
                INSERT INTO enrollments (
                    company_id, user_id, course_id, status, progress_percent
                )
                VALUES ('company-a', ?, ?, 'in_progress', 75)
                """,
                (self.user_id, other_course_id),
            )

        summary = CompanyTeamRepository().get_learning_summary(
            self.db_path,
            "company-a",
            self.user_id,
        )

        self.assertIsNotNone(summary)
        self.assertEqual(summary.started_courses_count, 0)
        self.assertEqual(summary.completed_courses_count, 0)
        self.assertEqual(summary.average_progress_percent, 0)

    def test_nonmember_cannot_write_learning_data_to_another_company(self) -> None:
        other_course_id = CourseRepository().save(
            self.db_path, "other-safety", "Other Safety", None, 0, "company-b"
        )
        LessonRepository().save(
            self.db_path,
            other_course_id,
            "lesson-1",
            "Lesson",
            "",
            None,
            None,
            0,
        )
        repository = ProgressRepository()

        repository.start_course_for_user(
            self.db_path,
            self.user_id,
            "other-safety",
            "company-b",
        )
        repository.complete_lesson_for_user(
            self.db_path,
            self.user_id,
            "other-safety",
            "lesson-1",
            "company-b",
        )
        self.assertFalse(
            repository.assign_course_to_user(
                self.db_path,
                self.user_id,
                "other-safety",
                company_id="company-b",
            )
        )

        self.assertEqual(
            repository.get_course_progress_for_user(
                self.db_path,
                self.user_id,
                "other-safety",
                "company-b",
            ),
            ("not_started", 0),
        )
        self.assertEqual(
            repository.get_resume_lesson_index_for_user(
                self.db_path,
                self.user_id,
                "other-safety",
                "company-b",
            ),
            0,
        )

    def test_assignment_author_must_be_an_active_company_member(self) -> None:
        upsert_telegram_user(
            self.db_path,
            202,
            "company-b-learner",
            "Company B",
            "Learner",
        )
        with get_connection(self.db_path) as connection:
            target_user_id = int(
                connection.execute(
                    "SELECT id FROM users WHERE telegram_id = 202"
                ).fetchone()["id"]
            )
            connection.execute(
                """
                INSERT INTO company_memberships (company_id, user_id, role)
                VALUES ('company-b', ?, 'student')
                """,
                (target_user_id,),
            )
        CourseRepository().save(
            self.db_path,
            "other-safety",
            "Other Safety",
            None,
            0,
            "company-b",
        )

        assigned = ProgressRepository().assign_course_to_user(
            self.db_path,
            target_user_id,
            "other-safety",
            company_id="company-b",
            assigned_by_user_id=self.user_id,
        )

        self.assertFalse(assigned)

    def test_quiz_attempts_do_not_cross_company_boundary(self) -> None:
        attempt_id = quiz_repository.create_attempt_for_user(
            self.db_path,
            self.user_id,
            "safety",
            quiz_version=1,
            questions_count=1,
            company_id="company-a",
        )
        assert attempt_id is not None
        quiz_repository.finish_attempt(self.db_path, attempt_id)

        self.assertEqual(
            quiz_repository.get_course_quiz_stats_for_user(
                self.db_path, self.user_id, "safety", "company-a"
            )["attempts_count"],
            1,
        )
        self.assertEqual(
            quiz_repository.get_course_quiz_stats_for_user(
                self.db_path, self.user_id, "safety", "company-b"
            )["attempts_count"],
            0,
        )

    def test_practical_attempts_do_not_cross_company_boundary(self) -> None:
        attempt_id = practical_task_attempt_repository.create_attempt_for_user(
            self.db_path,
            self.user_id,
            "safety",
            "lesson-1",
            "Task",
            "Description",
            "Expected",
            "Answer",
            company_id="company-a",
        )
        assert attempt_id is not None

        self.assertIsNotNone(
            practical_task_attempt_repository.get_attempt(
                self.db_path, attempt_id, "company-a"
            )
        )
        self.assertIsNone(
            practical_task_attempt_repository.get_attempt(
                self.db_path, attempt_id, "company-b"
            )
        )
        self.assertEqual(
            practical_task_attempt_repository.get_attempts_for_lesson_for_user(
                self.db_path,
                self.user_id,
                "safety",
                "lesson-1",
                company_id="company-b",
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
