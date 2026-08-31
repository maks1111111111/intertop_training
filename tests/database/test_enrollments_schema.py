"""Schema and migration tests for course assignment authorship."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.migrations import (
    migrate_enrollments_assignment_author,
    migrate_enrollments_due_at,
)


class EnrollmentAssignmentAuthorSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_initialize_database_creates_assignment_author_column(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            columns = {
                row["name"]: row
                for row in connection.execute(
                    "PRAGMA table_info(enrollments)"
                ).fetchall()
            }

        self.assertIn("assigned_by_user_id", columns)
        self.assertFalse(bool(columns["assigned_by_user_id"]["notnull"]))
        self.assertIsNone(columns["assigned_by_user_id"]["dflt_value"])

    def test_initialize_database_creates_assignment_author_index(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            indexes = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA index_list(enrollments)"
                ).fetchall()
            }

        self.assertIn(
            "idx_enrollments_assigned_by_user_id",
            indexes,
        )

    def test_initialize_database_creates_due_at_column(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            columns = {
                row["name"]: row
                for row in connection.execute(
                    "PRAGMA table_info(enrollments)"
                ).fetchall()
            }

        self.assertIn("due_at", columns)
        self.assertFalse(bool(columns["due_at"]["notnull"]))
        self.assertIsNone(columns["due_at"]["dflt_value"])

    def test_assignment_author_foreign_key_uses_set_null(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(enrollments)"
            ).fetchall()

        matching = [
            row
            for row in foreign_keys
            if row["from"] == "assigned_by_user_id"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["table"], "users")
        self.assertEqual(matching[0]["to"], "id")
        self.assertEqual(matching[0]["on_delete"], "SET NULL")

    def test_legacy_migration_preserves_existing_enrollment(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY
                );

                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE
                );

                CREATE TABLE enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'assigned',
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(user_id, course_id),
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (course_id)
                        REFERENCES courses(id)
                        ON DELETE CASCADE
                );

                INSERT INTO users (id) VALUES (1);
                INSERT INTO courses (id, slug) VALUES (10, 'alpha');

                INSERT INTO enrollments (
                    id,
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    assigned_at,
                    started_at
                )
                VALUES (
                    7,
                    1,
                    10,
                    'in_progress',
                    40,
                    '2026-08-01 10:00:00',
                    '2026-08-01 10:00:00'
                );
                """
            )

            migrate_enrollments_assignment_author(connection)
            connection.commit()

            row = connection.execute(
                """
                SELECT
                    id,
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    assigned_at,
                    assigned_by_user_id,
                    started_at
                FROM enrollments
                WHERE id = 7
                """
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], 7)
        self.assertEqual(row["user_id"], 1)
        self.assertEqual(row["course_id"], 10)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["progress_percent"], 40)
        self.assertEqual(row["assigned_at"], "2026-08-01 10:00:00")
        self.assertEqual(row["started_at"], "2026-08-01 10:00:00")

        # Legacy history must not be guessed.
        self.assertIsNone(row["assigned_by_user_id"])

    def test_due_at_migration_preserves_existing_enrollment(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY
                );

                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE
                );

                CREATE TABLE enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'assigned',
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    assigned_by_user_id INTEGER,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(user_id, course_id),
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (course_id)
                        REFERENCES courses(id)
                        ON DELETE CASCADE
                );

                INSERT INTO users (id) VALUES (1);
                INSERT INTO courses (id, slug) VALUES (10, 'alpha');

                INSERT INTO enrollments (
                    id,
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    assigned_at,
                    started_at
                )
                VALUES (
                    7,
                    1,
                    10,
                    'assigned',
                    0,
                    '2026-08-01 10:00:00',
                    NULL
                );
                """
            )

            migrate_enrollments_due_at(connection)
            connection.commit()

            row = connection.execute(
                """
                SELECT due_at
                FROM enrollments
                WHERE id = 7
                """
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertIsNone(row["due_at"])

    def test_due_at_migration_is_idempotent(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            migrate_enrollments_due_at(connection)
            migrate_enrollments_due_at(connection)

            columns = [
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(enrollments)"
                ).fetchall()
            ]

        self.assertEqual(columns.count("due_at"), 1)

    def test_migration_is_idempotent(self) -> None:
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            migrate_enrollments_assignment_author(connection)
            migrate_enrollments_assignment_author(connection)

            columns = [
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(enrollments)"
                ).fetchall()
            ]
            indexes = [
                row["name"]
                for row in connection.execute(
                    "PRAGMA index_list(enrollments)"
                ).fetchall()
            ]

        self.assertEqual(columns.count("assigned_by_user_id"), 1)
        self.assertEqual(
            indexes.count("idx_enrollments_assigned_by_user_id"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
