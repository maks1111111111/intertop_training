"""Tests for the read-only platform administration preflight audit."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.platform_audit import audit_platform_data, format_report, run
from app.repositories.company_repository import CompanyRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository


class PlatformAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "training.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            self.owner_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('platform-owner')"
                ).lastrowid
            )
        PlatformAdminRepository().bootstrap_owner(self.db_path, self.owner_id)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_clean_database_returns_clean_report_and_zero_exit_code(self) -> None:
        report = audit_platform_data(self.db_path)

        self.assertTrue(report.is_clean)
        self.assertEqual(
            format_report(report),
            "PLATFORM_AUDIT\nfindings=0\nstatus=clean",
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = run(["--db", str(self.db_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), format_report(report))

    def test_audit_reports_missing_trigger_owner_and_quota_breach_without_writes(self) -> None:
        CompanyRepository().create(self.db_path, "company-a", "Company A")
        with get_connection(self.db_path) as connection:
            connection.execute("DROP TRIGGER enforce_company_course_limit_update")
            connection.execute("UPDATE users SET is_active = 0 WHERE id = ?", (self.owner_id,))
            connection.executemany(
                "INSERT INTO courses (company_id, slug, title) VALUES ('company-a', ?, ?)",
                (("one", "One"), ("two", "Two")),
            )
            connection.execute(
                """INSERT INTO company_usage_limits (company_id, max_courses)
                   VALUES ('company-a', 1)"""
            )
            before_courses = int(
                connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
            )

        report = audit_platform_data(self.db_path)

        with get_connection(self.db_path) as connection:
            after_courses = int(
                connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
            )

        self.assertEqual(before_courses, after_courses)
        self.assertFalse(report.is_clean)
        self.assertEqual(
            {finding.code for finding in report.findings},
            {
                "missing_platform_trigger",
                "invalid_usable_owner_count",
                "course_limit_exceeded",
            },
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = run(["--db", str(self.db_path)])
        self.assertEqual(exit_code, 1)
        self.assertIn("status=review_required", stdout.getvalue())
        self.assertIn("code=course_limit_exceeded", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
