"""Tests for the strictly read-only company offboarding purge plan."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.database.company_purge_plan import (
    CompanyPurgePlanError,
    build_company_purge_plan,
    format_company_purge_plan,
)
from app.database.db import initialize_database


class CompanyPurgePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.db_path = self.root / "training.db"
        self.courses_dir = self.root / "courses"
        self.uploads_dir = self.root / "uploads"
        self.courses_dir.mkdir()
        self.uploads_dir.mkdir()
        initialize_database(self.db_path)
        self._seed_eligible_company()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _seed_eligible_company(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO companies (id, name, is_active) VALUES ('alpha', 'Alpha Ltd', 0)"
            )
            connection.execute(
                "INSERT INTO users (id, first_name) VALUES (1, 'Alice'), (2, 'Shared')"
            )
            connection.execute(
                "INSERT INTO companies (id, name) VALUES ('bravo', 'Bravo Ltd')"
            )
            connection.execute(
                """
                INSERT INTO company_memberships (company_id, user_id, role)
                VALUES ('alpha', 1, 'student'), ('alpha', 2, 'student'),
                       ('bravo', 2, 'student')
                """
            )
            connection.execute(
                """
                INSERT INTO courses (id, company_id, slug, title)
                VALUES (10, 'alpha', 'alpha-course', 'Alpha course')
                """
            )
            connection.execute(
                "INSERT INTO lessons (course_id, title) VALUES (10, 'Lesson')"
            )
            connection.execute(
                """
                INSERT INTO enrollments (company_id, user_id, course_id)
                VALUES ('alpha', 1, 10)
                """
            )
            connection.execute(
                """
                INSERT INTO platform_audit_events
                    (action, target_type, target_id, reason, created_at)
                VALUES ('company.deactivated', 'company', 'alpha', 'contract ended',
                        '2026-08-01 10:00:00')
                """
            )
        (self.courses_dir / "alpha").mkdir()
        (self.courses_dir / "alpha" / "alpha-course").mkdir()
        (self.courses_dir / "alpha" / "alpha-course" / "course.json").write_text(
            "{}", encoding="utf-8"
        )
        (self.uploads_dir / "alpha").mkdir()
        (self.uploads_dir / "alpha" / "source.pdf").write_bytes(b"source")

    def test_counts_only_eligible_company_data_without_mutating_it(self) -> None:
        with patch(
            "app.database.company_purge_plan.assess_company_offboarding"
        ) as assessment:
            assessment.return_value = _eligible_status()
            before = self.db_path.read_bytes()
            plan = build_company_purge_plan(
                db_path=self.db_path,
                company_id="alpha",
                courses_dir=self.courses_dir,
                uploads_dir=self.uploads_dir,
            )

        self.assertEqual(plan.record_counts["company"], 1)
        self.assertEqual(plan.record_counts["memberships"], 2)
        self.assertEqual(plan.record_counts["orphanable_user_accounts"], 1)
        self.assertEqual(plan.record_counts["courses"], 1)
        self.assertEqual(plan.course_directories, 1)
        self.assertEqual(plan.upload_files, 1)
        self.assertEqual(plan.upload_bytes, len(b"source"))
        self.assertEqual(before, self.db_path.read_bytes())
        self.assertIn("status=dry_run_only", format_company_purge_plan(plan))

    def test_refuses_to_plan_before_the_grace_period_ends(self) -> None:
        with patch(
            "app.database.company_purge_plan.assess_company_offboarding",
            return_value=_ineligible_status(),
        ):
            with self.assertRaisesRegex(CompanyPurgePlanError, "not eligible"):
                build_company_purge_plan(
                    db_path=self.db_path,
                    company_id="alpha",
                    courses_dir=self.courses_dir,
                    uploads_dir=self.uploads_dir,
                )

    def test_refuses_symbolic_links_in_company_uploads(self) -> None:
        target = self.root / "outside.txt"
        target.write_text("outside", encoding="utf-8")
        (self.uploads_dir / "alpha" / "linked.txt").symlink_to(target)
        with patch(
            "app.database.company_purge_plan.assess_company_offboarding",
            return_value=_eligible_status(),
        ):
            with self.assertRaisesRegex(CompanyPurgePlanError, "symbolic link"):
                build_company_purge_plan(
                    db_path=self.db_path,
                    company_id="alpha",
                    courses_dir=self.courses_dir,
                    uploads_dir=self.uploads_dir,
                )


def _eligible_status():
    from app.database.company_offboarding import CompanyOffboardingStatus

    return CompanyOffboardingStatus(
        company_id="alpha",
        company_name="Alpha Ltd",
        is_active=False,
        deactivated_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
        eligible_at=datetime(2026, 8, 31, 10, tzinfo=timezone.utc),
        is_eligible=True,
        reason="working-data deletion window has opened",
    )


def _ineligible_status():
    from app.database.company_offboarding import CompanyOffboardingStatus

    return CompanyOffboardingStatus(
        company_id="alpha",
        company_name="Alpha Ltd",
        is_active=False,
        deactivated_at=datetime(2026, 9, 20, 10, tzinfo=timezone.utc),
        eligible_at=datetime(2026, 10, 20, 10, tzinfo=timezone.utc),
        is_eligible=False,
        reason="working-data grace period is still active",
    )
