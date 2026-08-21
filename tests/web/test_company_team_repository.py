"""Tests for tenant-scoped company team learning summaries."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.repositories.company_team_repository import CompanyTeamRepository


class CompanyTeamRepositoryTests(unittest.TestCase):
    """Verify tenant isolation and aggregate learning metrics."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"
        self.repository = CompanyTeamRepository()

        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE company_memberships (
                    id INTEGER PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE enrollments (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_user(
        self,
        user_id: int,
        username: str,
        first_name: str,
        company_id: str,
        role: str = "student",
        membership_active: int = 1,
        user_active: int = 1,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id,
                    username,
                    first_name,
                    last_name,
                    is_active
                )
                VALUES (?, ?, ?, '', ?)
                """,
                (
                    user_id,
                    username,
                    first_name,
                    user_active,
                ),
            )
            connection.execute(
                """
                INSERT INTO company_memberships (
                    id,
                    company_id,
                    user_id,
                    role,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    company_id,
                    user_id,
                    role,
                    membership_active,
                ),
            )

    def _insert_enrollment(
        self,
        enrollment_id: int,
        user_id: int,
        status: str,
        progress_percent: int,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO enrollments (
                    id,
                    user_id,
                    status,
                    progress_percent
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    enrollment_id,
                    user_id,
                    status,
                    progress_percent,
                ),
            )

    def test_returns_only_active_members_of_requested_company(self) -> None:
        self._insert_user(1, "alice", "Alice", "company-a")
        self._insert_user(2, "bob", "Bob", "company-b")
        self._insert_user(
            3,
            "inactive-membership",
            "Inactive Membership",
            "company-a",
            membership_active=0,
        )
        self._insert_user(
            4,
            "inactive-user",
            "Inactive User",
            "company-a",
            user_active=0,
        )

        records = self.repository.list_learning_summary(
            self.db_path,
            "company-a",
        )

        self.assertEqual(
            [record.user_id for record in records],
            [1],
        )

    def test_aggregates_started_completed_and_average_progress(self) -> None:
        self._insert_user(1, "alice", "Alice", "company-a")

        self._insert_enrollment(1, 1, "in_progress", 40)
        self._insert_enrollment(2, 1, "completed", 100)
        self._insert_enrollment(3, 1, "assigned", 0)

        records = self.repository.list_learning_summary(
            self.db_path,
            "company-a",
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.started_courses_count, 2)
        self.assertEqual(record.completed_courses_count, 1)
        self.assertEqual(record.average_progress_percent, 70)

    def test_member_without_started_courses_gets_zero_metrics(self) -> None:
        self._insert_user(
            1,
            "manager",
            "Manager",
            "company-a",
            role="manager",
        )

        records = self.repository.list_learning_summary(
            self.db_path,
            "company-a",
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.role, "manager")
        self.assertEqual(record.started_courses_count, 0)
        self.assertEqual(record.completed_courses_count, 0)
        self.assertEqual(record.average_progress_percent, 0)

    def test_company_id_is_required(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.list_learning_summary(
                self.db_path,
                "   ",
            )


if __name__ == "__main__":
    unittest.main()
