"""Tests for the read-only multi-company data preflight audit."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.database.tenant_audit import audit_tenant_data, format_report, run
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_repository import LessonRepository


class TenantAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "training.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            connection.executemany(
                "INSERT INTO companies (id, name) VALUES (?, ?)",
                (("company-a", "Company A"), ("company-b", "Company B")),
            )
        upsert_telegram_user(self.db_path, 101, "learner", "Learner", "One")
        with get_connection(self.db_path) as connection:
            self.user_id = int(
                connection.execute(
                    "SELECT id FROM users WHERE telegram_id = 101"
                ).fetchone()["id"]
            )
        CompanyMembershipRepository().add(
            self.db_path,
            "company-a",
            self.user_id,
        )
        self.course_a_id = CourseRepository().save(
            self.db_path,
            "alpha",
            "Alpha",
            None,
            0,
            "company-a",
        )
        self.course_b_id = CourseRepository().save(
            self.db_path,
            "beta",
            "Beta",
            None,
            0,
            "company-b",
        )
        LessonRepository().save(
            self.db_path,
            self.course_a_id,
            "lesson-a",
            "Lesson A",
            "",
            None,
            None,
            0,
        )
        self.lesson_b_id = LessonRepository().save(
            self.db_path,
            self.course_b_id,
            "lesson-b",
            "Lesson B",
            "",
            None,
            None,
            0,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_clean_database_returns_clean_report_and_exit_code_zero(self) -> None:
        report = audit_tenant_data(self.db_path)

        self.assertTrue(report.is_clean)
        self.assertEqual(format_report(report), "TENANT_AUDIT\nfindings=0\nstatus=clean")

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = run(["--db", str(self.db_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), format_report(report))

    def test_audit_reports_cross_tenant_and_membership_anomalies_without_mutation(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "DROP TRIGGER enforce_enrollment_course_company_insert"
            )
            connection.execute(
                "DROP TRIGGER enforce_lesson_progress_course_company_insert"
            )
            connection.execute(
                "DROP TRIGGER enforce_quiz_attempt_course_company_insert"
            )
            connection.execute(
                "DROP TRIGGER enforce_practical_attempt_course_company_insert"
            )
            connection.execute(
                """
                INSERT INTO enrollments (
                    company_id, user_id, course_id, status, progress_percent
                )
                VALUES ('company-a', ?, ?, 'in_progress', 10)
                """,
                (self.user_id, self.course_b_id),
            )
            connection.execute(
                """
                INSERT INTO lesson_progress (company_id, user_id, lesson_id, status)
                VALUES ('company-a', ?, ?, 'completed')
                """,
                (self.user_id, self.lesson_b_id),
            )
            connection.execute(
                """
                INSERT INTO quiz_attempts (
                    company_id, user_id, course_slug, quiz_version,
                    started_at, questions_count
                )
                VALUES ('company-a', ?, 'beta', 1, CURRENT_TIMESTAMP, 1)
                """,
                (self.user_id,),
            )
            connection.execute(
                """
                INSERT INTO practical_task_attempts (
                    company_id, user_id, course_slug, lesson_slug,
                    task_title, task_description, expected_result, learner_answer
                )
                VALUES ('company-a', ?, 'beta', 'lesson-b', 'Task', 'Description',
                        'Expected', 'Answer')
                """,
                (self.user_id,),
            )
            connection.execute(
                """
                INSERT INTO courses (company_id, slug, title)
                VALUES ('missing-company', 'orphaned', 'Orphaned')
                """
            )
            before_count = connection.execute(
                "SELECT COUNT(*) FROM enrollments"
            ).fetchone()[0]

        report = audit_tenant_data(self.db_path)

        with get_connection(self.db_path) as connection:
            after_count = connection.execute(
                "SELECT COUNT(*) FROM enrollments"
            ).fetchone()[0]

        self.assertFalse(report.is_clean)
        self.assertEqual(before_count, after_count)
        self.assertEqual(
            {(finding.code, finding.table_name) for finding in report.findings},
            {
                ("unknown_company", "courses"),
                ("course_company_mismatch", "enrollments"),
                ("lesson_company_mismatch", "lesson_progress"),
                ("assessment_course_company_mismatch", "quiz_attempts"),
                ("assessment_course_company_mismatch", "practical_task_attempts"),
            },
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = run(["--db", str(self.db_path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("status=review_required", stdout.getvalue())
        self.assertIn("code=course_company_mismatch", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
