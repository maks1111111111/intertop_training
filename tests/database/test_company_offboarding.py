"""Tests for the non-destructive company offboarding eligibility check."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.database.company_offboarding import (
    CompanyOffboardingError,
    assess_company_offboarding,
    format_company_offboarding_status,
)
from app.database.db import initialize_database


class CompanyOffboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "training.db"
        initialize_database(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO companies (id, name, is_active) VALUES ('alpha', 'Alpha Ltd', 0)"
            )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _event(self, action: str, created_at: str) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO platform_audit_events
                    (action, target_type, target_id, reason, created_at)
                VALUES (?, 'company', 'alpha', 'test', ?)
                """,
                (action, created_at),
            )

    def test_becomes_eligible_only_after_thirty_days_from_audited_deactivation(self) -> None:
        self._event("company.deactivated", "2026-08-01 10:00:00")

        pending = assess_company_offboarding(
            self.db_path,
            "alpha",
            now=lambda: datetime(2026, 8, 31, 9, 59, 59, tzinfo=timezone.utc),
        )
        eligible = assess_company_offboarding(
            self.db_path,
            "alpha",
            now=lambda: datetime(2026, 8, 31, 10, 0, 0, tzinfo=timezone.utc),
        )

        self.assertFalse(pending.is_eligible)
        self.assertTrue(eligible.is_eligible)
        self.assertEqual(eligible.eligible_at, datetime(2026, 8, 31, 10, tzinfo=timezone.utc))
        self.assertIn("eligible=true", format_company_offboarding_status(eligible))
        self.assertIn("status=read_only", format_company_offboarding_status(eligible))

    def test_reactivation_blocks_an_older_deactivation_window(self) -> None:
        self._event("company.deactivated", "2026-08-01 10:00:00")
        self._event("company.activated", "2026-08-02 10:00:00")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE companies SET is_active = 1 WHERE id = 'alpha'")

        status = assess_company_offboarding(
            self.db_path,
            "alpha",
            now=lambda: datetime(2026, 10, 1, tzinfo=timezone.utc),
        )

        self.assertFalse(status.is_eligible)
        self.assertEqual(status.reason, "company is active")

    def test_inactive_company_without_an_audited_deactivation_is_not_eligible(self) -> None:
        status = assess_company_offboarding(
            self.db_path,
            "alpha",
            now=lambda: datetime(2026, 10, 1, tzinfo=timezone.utc),
        )

        self.assertFalse(status.is_eligible)
        self.assertEqual(status.reason, "no current audited deactivation event")

    def test_unknown_company_is_rejected(self) -> None:
        with self.assertRaisesRegex(CompanyOffboardingError, "does not exist"):
            assess_company_offboarding(
                self.db_path,
                "unknown",
                now=lambda: datetime(2026, 10, 1, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
