"""Database constraints that preserve learning-data tenant ownership."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.migrations import migrate_web_lesson_progress_tenant_scope


class LearningTenantIntegritySchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "training.db"
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            connection.executemany(
                "INSERT INTO companies (id, name) VALUES (?, ?)",
                (("company-a", "Company A"), ("company-b", "Company B")),
            )
            self.user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('learner')"
                ).lastrowid
            )
            self.course_a_id = int(
                connection.execute(
                    """
                    INSERT INTO courses (company_id, slug, title)
                    VALUES ('company-a', 'course-a', 'Course A')
                    """
                ).lastrowid
            )
            self.course_b_id = int(
                connection.execute(
                    """
                    INSERT INTO courses (company_id, slug, title)
                    VALUES ('company-b', 'course-b', 'Course B')
                    """
                ).lastrowid
            )
            self.lesson_a_id = int(
                connection.execute(
                    "INSERT INTO lessons (course_id, title) VALUES (?, 'Lesson A')",
                    (self.course_a_id,),
                ).lastrowid
            )
            self.lesson_b_id = int(
                connection.execute(
                    "INSERT INTO lessons (course_id, title) VALUES (?, 'Lesson B')",
                    (self.course_b_id,),
                ).lastrowid
            )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_enrollment_must_belong_to_its_company_course(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "enrollment course belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO enrollments (company_id, user_id, course_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.course_b_id),
                )

            enrollment_id = int(
                connection.execute(
                    """
                    INSERT INTO enrollments (company_id, user_id, course_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.course_a_id),
                ).lastrowid
            )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "enrollment course belongs to another company",
            ):
                connection.execute(
                    "UPDATE enrollments SET company_id = 'company-b' WHERE id = ?",
                    (enrollment_id,),
                )

    def test_course_company_ownership_is_immutable(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "course company ownership is immutable",
            ):
                connection.execute(
                    "UPDATE courses SET company_id = 'company-b' WHERE id = ?",
                    (self.course_a_id,),
                )

    def test_lesson_progress_must_belong_to_its_company_course(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "lesson belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO lesson_progress (company_id, user_id, lesson_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.lesson_b_id),
                )

            progress_id = int(
                connection.execute(
                    """
                    INSERT INTO lesson_progress (company_id, user_id, lesson_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.lesson_a_id),
                ).lastrowid
            )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "lesson belongs to another company",
            ):
                connection.execute(
                    "UPDATE lesson_progress SET company_id = 'company-b' WHERE id = ?",
                    (progress_id,),
                )

    def test_assessment_attempts_must_belong_to_their_company_course(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "quiz course belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        company_id, user_id, course_slug, quiz_version,
                        started_at, questions_count
                    )
                    VALUES ('company-a', ?, 'course-b', 1, CURRENT_TIMESTAMP, 1)
                    """,
                    (self.user_id,),
                )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "practical-task course belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO practical_task_attempts (
                        company_id, user_id, course_slug, lesson_slug,
                        task_title, task_description, expected_result, learner_answer
                    )
                    VALUES ('company-a', ?, 'course-b', 'lesson', 'Task', 'Description',
                            'Expected', 'Answer')
                    """,
                    (self.user_id,),
                )

            quiz_id = int(
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        company_id, user_id, course_slug, quiz_version,
                        started_at, questions_count
                    )
                    VALUES ('company-a', ?, 'course-a', 1, CURRENT_TIMESTAMP, 1)
                    """,
                    (self.user_id,),
                ).lastrowid
            )
            practical_id = int(
                connection.execute(
                    """
                    INSERT INTO practical_task_attempts (
                        company_id, user_id, course_slug, lesson_slug,
                        task_title, task_description, expected_result, learner_answer
                    )
                    VALUES ('company-a', ?, 'course-a', 'lesson', 'Task', 'Description',
                            'Expected', 'Answer')
                    """,
                    (self.user_id,),
                ).lastrowid
            )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "quiz course belongs to another company",
            ):
                connection.execute(
                    "UPDATE quiz_attempts SET company_id = 'company-b' WHERE id = ?",
                    (quiz_id,),
                )
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "practical-task course belongs to another company",
            ):
                connection.execute(
                    "UPDATE practical_task_attempts SET company_id = 'company-b' WHERE id = ?",
                    (practical_id,),
                )

    def test_legacy_company_has_the_same_assessment_integrity_guards(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "quiz course belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        company_id, user_id, course_slug, quiz_version,
                        started_at, questions_count
                    )
                    VALUES ('intertop', ?, 'missing-course', 1, CURRENT_TIMESTAMP, 1)
                    """,
                    (self.user_id,),
                )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "practical-task course belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO practical_task_attempts (
                        company_id, user_id, course_slug, lesson_slug,
                        task_title, task_description, expected_result, learner_answer
                    )
                    VALUES ('intertop', ?, 'missing-course', 'lesson',
                            'Task', 'Description', 'Expected', 'Answer')
                    """,
                    (self.user_id,),
                )

    def test_reinitialization_replaces_legacy_bypass_trigger(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "DROP TRIGGER enforce_quiz_attempt_course_company_insert"
            )
            connection.executescript(
                """
                CREATE TRIGGER enforce_quiz_attempt_course_company_insert
                BEFORE INSERT ON quiz_attempts
                FOR EACH ROW
                WHEN NEW.company_id != 'intertop'
                BEGIN
                    SELECT RAISE(ABORT, 'legacy trigger');
                END;
                """
            )

        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            trigger_sql = str(
                connection.execute(
                    """
                    SELECT sql
                    FROM sqlite_master
                    WHERE type = 'trigger'
                      AND name = 'enforce_quiz_attempt_course_company_insert'
                    """
                ).fetchone()["sql"]
            )
        self.assertNotIn("NEW.company_id != 'intertop'", trigger_sql)
        self.assertIn("WHEN NOT EXISTS", trigger_sql)

    def test_legacy_web_progress_is_unique_per_company(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO web_lesson_progress (
                    company_id, user_id, course_slug, lesson_id
                )
                VALUES ('company-a', 'shared-user', 'same-course', 'lesson-1')
                """
            )
            connection.execute(
                """
                INSERT INTO web_lesson_progress (
                    company_id, user_id, course_slug, lesson_id
                )
                VALUES ('company-b', 'shared-user', 'same-course', 'lesson-1')
                """
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM web_lesson_progress"
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_web_progress_migration_preserves_legacy_rows(self) -> None:
        legacy_path = Path(self._tmpdir.name) / "legacy-progress.db"
        with sqlite3.connect(legacy_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                CREATE TABLE web_lesson_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    course_slug TEXT NOT NULL,
                    lesson_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, course_slug, lesson_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO web_lesson_progress (
                    user_id, course_slug, lesson_id, completed_at
                )
                VALUES ('legacy-user', 'course', 'lesson', '2026-09-10 09:00:00')
                """
            )

            migrate_web_lesson_progress_tenant_scope(connection)

            row = connection.execute(
                """
                SELECT id, company_id, user_id, course_slug, lesson_id, completed_at
                FROM web_lesson_progress
                """
            ).fetchone()
            self.assertEqual(
                tuple(row),
                (1, "intertop", "legacy-user", "course", "lesson", "2026-09-10 09:00:00"),
            )

            connection.execute(
                """
                INSERT INTO web_lesson_progress (
                    company_id, user_id, course_slug, lesson_id
                )
                VALUES ('company-b', 'legacy-user', 'course', 'lesson')
                """
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM web_lesson_progress"
            ).fetchone()[0]

        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
