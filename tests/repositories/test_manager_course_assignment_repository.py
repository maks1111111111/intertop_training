"""Tests for tenant-scoped manager course assignment history."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.repositories.manager_course_assignment_repository import (
    ManagerCourseAssignmentRecord,
    ManagerCourseAssignmentRepository,
)


class ManagerCourseAssignmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"
        self.repository = ManagerCourseAssignmentRepository()

        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE company_memberships (
                    id INTEGER PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL
                );

                CREATE TABLE enrollments (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    assigned_at TEXT NOT NULL,
                    assigned_by_user_id INTEGER,
                    started_at TEXT,
                    completed_at TEXT
                );
                """
            )

            connection.executemany(
                """
                INSERT INTO users (id, username, is_active)
                VALUES (?, ?, ?)
                """,
                (
                    (1, "manager", 1),
                    (2, "employee-a", 1),
                    (3, "employee-b", 1),
                    (4, "inactive-user", 0),
                ),
            )

            connection.executemany(
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
                    (1, "company-a", 1, "manager", 1),
                    (2, "company-a", 2, "student", 1),
                    (3, "company-b", 3, "student", 1),
                    (4, "company-a", 4, "student", 1),
                ),
            )

            connection.executemany(
                """
                INSERT INTO courses (id, slug, title)
                VALUES (?, ?, ?)
                """,
                (
                    (10, "alpha", "Alpha Course"),
                    (11, "beta", "Beta Course"),
                    (12, "gamma", "Gamma Course"),
                    (13, "legacy", "Legacy Course"),
                    (14, "self-start", "Self Start Course"),
                ),
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_enrollment(
        self,
        *,
        enrollment_id: int,
        user_id: int,
        course_id: int,
        status: str,
        progress_percent: int,
        assigned_at: str,
        assigned_by_user_id: int | None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO enrollments (
                    id,
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    assigned_at,
                    assigned_by_user_id,
                    started_at,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enrollment_id,
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    assigned_at,
                    assigned_by_user_id,
                    started_at,
                    completed_at,
                ),
            )

    def test_returns_explicit_assignments_with_lifecycle_fields(self) -> None:
        self._insert_enrollment(
            enrollment_id=100,
            user_id=2,
            course_id=10,
            status="assigned",
            progress_percent=0,
            assigned_at="2026-08-31 10:00:00",
            assigned_by_user_id=1,
        )
        self._insert_enrollment(
            enrollment_id=101,
            user_id=2,
            course_id=11,
            status="in_progress",
            progress_percent=60,
            assigned_at="2026-08-31 11:00:00",
            assigned_by_user_id=1,
            started_at="2026-08-31 12:00:00",
        )
        self._insert_enrollment(
            enrollment_id=102,
            user_id=2,
            course_id=12,
            status="completed",
            progress_percent=100,
            assigned_at="2026-08-31 13:00:00",
            assigned_by_user_id=1,
            started_at="2026-08-31 14:00:00",
            completed_at="2026-08-31 15:00:00",
        )

        records = self.repository.list_for_member(
            self.db_path,
            "company-a",
            2,
        )

        self.assertEqual(
            records,
            (
                ManagerCourseAssignmentRecord(
                    employee_user_id=2,
                    course_slug="gamma",
                    course_title="Gamma Course",
                    status="completed",
                    progress_percent=100,
                    assigned_at="2026-08-31 13:00:00",
                    assigned_by_user_id=1,
                    started_at="2026-08-31 14:00:00",
                    completed_at="2026-08-31 15:00:00",
                ),
                ManagerCourseAssignmentRecord(
                    employee_user_id=2,
                    course_slug="beta",
                    course_title="Beta Course",
                    status="in_progress",
                    progress_percent=60,
                    assigned_at="2026-08-31 11:00:00",
                    assigned_by_user_id=1,
                    started_at="2026-08-31 12:00:00",
                    completed_at=None,
                ),
                ManagerCourseAssignmentRecord(
                    employee_user_id=2,
                    course_slug="alpha",
                    course_title="Alpha Course",
                    status="assigned",
                    progress_percent=0,
                    assigned_at="2026-08-31 10:00:00",
                    assigned_by_user_id=1,
                    started_at=None,
                    completed_at=None,
                ),
            ),
        )

    def test_excludes_legacy_and_self_started_enrollments(self) -> None:
        self._insert_enrollment(
            enrollment_id=100,
            user_id=2,
            course_id=13,
            status="assigned",
            progress_percent=0,
            assigned_at="2026-08-30 10:00:00",
            assigned_by_user_id=None,
        )
        self._insert_enrollment(
            enrollment_id=101,
            user_id=2,
            course_id=14,
            status="in_progress",
            progress_percent=40,
            assigned_at="2026-08-30 11:00:00",
            assigned_by_user_id=None,
            started_at="2026-08-30 11:00:00",
        )

        records = self.repository.list_for_member(
            self.db_path,
            "company-a",
            2,
        )

        self.assertEqual(records, ())

    def test_does_not_return_member_from_another_company(self) -> None:
        self._insert_enrollment(
            enrollment_id=100,
            user_id=3,
            course_id=10,
            status="assigned",
            progress_percent=0,
            assigned_at="2026-08-31 10:00:00",
            assigned_by_user_id=1,
        )

        records = self.repository.list_for_member(
            self.db_path,
            "company-a",
            3,
        )

        self.assertEqual(records, ())

    def test_inactive_membership_returns_no_assignments(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE company_memberships
                SET is_active = 0
                WHERE company_id = 'company-a'
                  AND user_id = 2
                """
            )

        self._insert_enrollment(
            enrollment_id=100,
            user_id=2,
            course_id=10,
            status="assigned",
            progress_percent=0,
            assigned_at="2026-08-31 10:00:00",
            assigned_by_user_id=1,
        )

        records = self.repository.list_for_member(
            self.db_path,
            "company-a",
            2,
        )

        self.assertEqual(records, ())

    def test_inactive_user_returns_no_assignments(self) -> None:
        self._insert_enrollment(
            enrollment_id=100,
            user_id=4,
            course_id=10,
            status="assigned",
            progress_percent=0,
            assigned_at="2026-08-31 10:00:00",
            assigned_by_user_id=1,
        )

        records = self.repository.list_for_member(
            self.db_path,
            "company-a",
            4,
        )

        self.assertEqual(records, ())

    def test_empty_assignment_history_returns_empty_tuple(self) -> None:
        records = self.repository.list_for_member(
            self.db_path,
            "company-a",
            2,
        )

        self.assertEqual(records, ())

    def test_invalid_company_ids_are_rejected(self) -> None:
        for invalid in ("", "   ", 123, None):
            with self.subTest(company_id=invalid):
                with self.assertRaises(ValueError):
                    self.repository.list_for_member(
                        self.db_path,
                        invalid,  # type: ignore[arg-type]
                        2,
                    )

    def test_invalid_user_ids_are_rejected(self) -> None:
        for invalid in (0, -1, True, "2", None):
            with self.subTest(user_id=invalid):
                with self.assertRaises(ValueError):
                    self.repository.list_for_member(
                        self.db_path,
                        "company-a",
                        invalid,  # type: ignore[arg-type]
                    )


if __name__ == "__main__":
    unittest.main()
