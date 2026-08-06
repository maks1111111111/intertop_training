"""Tests for practical_task_attempts table initialization."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.database.db import get_connection, initialize_database

EXPECTED_COLUMNS = (
    "id",
    "user_id",
    "course_slug",
    "lesson_slug",
    "task_title",
    "task_description",
    "expected_result",
    "learner_answer",
    "score",
    "max_score",
    "passed",
    "feedback_summary",
    "feedback_strengths_json",
    "feedback_improvements_json",
    "status",
    "started_at",
    "reviewed_at",
)

EXPECTED_INDEXES = (
    "idx_practical_task_attempts_user_id",
    "idx_practical_task_attempts_course_lesson",
    "idx_practical_task_attempts_status",
)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row[1] for row in rows]


def _index_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA index_list({table_name})").fetchall()
    return [row[1] for row in rows]


def _insert_user(connection: sqlite3.Connection, telegram_id: int = 1001) -> int:
    cursor = connection.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        """,
        (telegram_id, "learner", "Test", "User"),
    )
    return int(cursor.lastrowid)


def _insert_minimal_attempt(
    connection: sqlite3.Connection,
    user_id: int,
    *,
    status: Optional[str] = None,
    score: Optional[int] = None,
    max_score: Optional[int] = None,
    passed: Optional[int] = None,
) -> int:
    columns = [
        "user_id",
        "course_slug",
        "lesson_slug",
        "task_title",
        "task_description",
        "expected_result",
        "learner_answer",
    ]
    values = [
        user_id,
        "safety",
        "lesson_01",
        "Inspect the work area",
        "Walk through the area and identify hazards.",
        "All hazards are documented and addressed.",
        "I checked the floor and removed loose cables.",
    ]

    if status is not None:
        columns.append("status")
        values.append(status)
    if score is not None:
        columns.append("score")
        values.append(score)
    if max_score is not None:
        columns.append("max_score")
        values.append(max_score)
    if passed is not None:
        columns.append("passed")
        values.append(passed)

    placeholders = ", ".join("?" for _ in values)
    column_list = ", ".join(columns)
    cursor = connection.execute(
        f"""
        INSERT INTO practical_task_attempts ({column_list})
        VALUES ({placeholders})
        """,
        values,
    )
    return int(cursor.lastrowid)


class PracticalTaskAttemptsSchemaTests(unittest.TestCase):
    """Schema initialization tests for practical_task_attempts."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_initialize_database_creates_table(self) -> None:
        with get_connection(self.db_path) as connection:
            self.assertTrue(_table_exists(connection, "practical_task_attempts"))

    def test_table_contains_expected_columns(self) -> None:
        with get_connection(self.db_path) as connection:
            columns = _column_names(connection, "practical_task_attempts")

        self.assertEqual(columns, list(EXPECTED_COLUMNS))

    def test_default_values_for_minimal_insert(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)
            attempt_id = _insert_minimal_attempt(connection, user_id)
            row = connection.execute(
                """
                SELECT status, started_at, score, max_score, passed,
                       feedback_summary, feedback_strengths_json,
                       feedback_improvements_json, reviewed_at
                FROM practical_task_attempts
                WHERE id = ?
                """,
                (attempt_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "pending")
        self.assertIsNotNone(row[1])
        self.assertIsNone(row[2])
        self.assertIsNone(row[3])
        self.assertIsNone(row[4])
        self.assertIsNone(row[5])
        self.assertIsNone(row[6])
        self.assertIsNone(row[7])
        self.assertIsNone(row[8])

    def test_foreign_key_rejects_unknown_user(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_minimal_attempt(connection, user_id=9999)

    def test_on_delete_cascade_removes_attempts(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)
            _insert_minimal_attempt(connection, user_id)
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            count = connection.execute(
                "SELECT COUNT(*) FROM practical_task_attempts"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_check_status_rejects_unknown_value(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_minimal_attempt(connection, user_id, status="archived")

    def test_check_passed_allows_null_zero_and_one(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)

            _insert_minimal_attempt(connection, user_id, passed=None)
            _insert_minimal_attempt(connection, user_id, passed=0)
            _insert_minimal_attempt(connection, user_id, passed=1)

            with self.assertRaises(sqlite3.IntegrityError):
                _insert_minimal_attempt(connection, user_id, passed=2)

    def test_check_score_and_max_score_reject_negative_values(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)

            _insert_minimal_attempt(connection, user_id, score=None, max_score=None)
            _insert_minimal_attempt(connection, user_id, score=0, max_score=0)

            with self.assertRaises(sqlite3.IntegrityError):
                _insert_minimal_attempt(connection, user_id, score=-1)

            with self.assertRaises(sqlite3.IntegrityError):
                _insert_minimal_attempt(connection, user_id, max_score=-1)

    def test_indexes_exist(self) -> None:
        with get_connection(self.db_path) as connection:
            index_names = _index_names(connection, "practical_task_attempts")

        for expected_name in EXPECTED_INDEXES:
            self.assertIn(expected_name, index_names)

    def test_initialize_database_is_idempotent(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)
            _insert_minimal_attempt(connection, user_id)

        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            self.assertTrue(_table_exists(connection, "practical_task_attempts"))
            for expected_name in EXPECTED_INDEXES:
                self.assertIn(
                    expected_name,
                    _index_names(connection, "practical_task_attempts"),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM practical_task_attempts"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_existing_database_is_upgraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"

            connection = sqlite3.connect(db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                """,
                (4242, "legacy", "Legacy", "User"),
            )
            connection.commit()
            connection.close()

            initialize_database(db_path)

            with get_connection(db_path) as upgraded:
                self.assertTrue(_table_exists(upgraded, "practical_task_attempts"))
                user_count = upgraded.execute(
                    "SELECT COUNT(*) FROM users WHERE telegram_id = ?",
                    (4242,),
                ).fetchone()[0]

        self.assertEqual(user_count, 1)


if __name__ == "__main__":
    unittest.main()
