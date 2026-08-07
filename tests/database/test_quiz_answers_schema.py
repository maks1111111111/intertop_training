"""Tests for quiz_answers uniqueness migration and repair."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database


LEGACY_QUIZ_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    role TEXT NOT NULL DEFAULT 'student',
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT
);

CREATE TABLE quiz_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    course_slug TEXT NOT NULL,
    quiz_version INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    questions_count INTEGER NOT NULL,
    correct_answers INTEGER DEFAULT 0,
    score_percent REAL DEFAULT 0,
    passed INTEGER DEFAULT 0,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE quiz_answers (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    selected_option_id TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    FOREIGN KEY (attempt_id)
        REFERENCES quiz_attempts(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_quiz_answers_attempt_id
    ON quiz_answers(attempt_id);
"""


def _index_exists(connection: sqlite3.Connection, index_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index' AND name = ?
        """,
        (index_name,),
    ).fetchone()
    return row is not None


def _answer_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, attempt_id, question_id, selected_option_id, is_correct
        FROM quiz_answers
        ORDER BY id
        """
    ).fetchall()


class QuizAnswersSchemaTests(unittest.TestCase):
    def test_fresh_database_has_unique_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fresh.db"
            initialize_database(db_path)

            with get_connection(db_path) as connection:
                self.assertTrue(
                    _index_exists(
                        connection,
                        "idx_quiz_answers_attempt_question",
                    )
                )

    def test_legacy_duplicate_rows_are_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            with get_connection(db_path) as connection:
                connection.executescript(LEGACY_QUIZ_SCHEMA)
                user_id = connection.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (1001, "learner", "Test", "User"),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        id, user_id, course_slug, quiz_version, questions_count
                    )
                    VALUES (1, ?, 'alpha', 1, 6)
                    """,
                    (user_id,),
                )
                connection.executescript(
                    """
                    INSERT INTO quiz_answers (
                        id, attempt_id, question_id, selected_option_id, is_correct
                    )
                    VALUES
                        (1, 1, 'q1', 'a', 1),
                        (2, 1, 'q1', 'b', 1),
                        (3, 1, 'q1', 'c', 0),
                        (4, 1, 'q2', 'a', 1);
                    """
                )

            initialize_database(db_path)

            with get_connection(db_path) as connection:
                rows = _answer_rows(connection)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["id"], 1)
                self.assertEqual(rows[0]["question_id"], "q1")
                self.assertEqual(rows[0]["selected_option_id"], "a")
                self.assertEqual(rows[1]["id"], 4)
                self.assertEqual(rows[1]["question_id"], "q2")
                self.assertTrue(
                    _index_exists(
                        connection,
                        "idx_quiz_answers_attempt_question",
                    )
                )

    def test_repair_keeps_first_answer_even_when_later_duplicate_is_correct(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "first-wins.db"
            with get_connection(db_path) as connection:
                connection.executescript(LEGACY_QUIZ_SCHEMA)
                user_id = connection.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (1001, "learner", "Test", "User"),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        id, user_id, course_slug, quiz_version, questions_count
                    )
                    VALUES (1, ?, 'alpha', 1, 1)
                    """,
                    (user_id,),
                )
                connection.executescript(
                    """
                    INSERT INTO quiz_answers (
                        id, attempt_id, question_id, selected_option_id, is_correct
                    )
                    VALUES
                        (1, 1, 'q1', 'a', 0),
                        (2, 1, 'q1', 'b', 1);
                    """
                )

            initialize_database(db_path)

            with get_connection(db_path) as connection:
                rows = _answer_rows(connection)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["id"], 1)
                self.assertEqual(rows[0]["selected_option_id"], "a")
                self.assertEqual(rows[0]["is_correct"], 0)

    def test_repair_recalculates_corrupted_finished_attempt_statistics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "corrupted-stats.db"
            with get_connection(db_path) as connection:
                connection.executescript(LEGACY_QUIZ_SCHEMA)
                user_id = connection.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (1001, "learner", "Test", "User"),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        id,
                        user_id,
                        course_slug,
                        quiz_version,
                        questions_count,
                        finished_at,
                        correct_answers,
                        score_percent,
                        passed
                    )
                    VALUES (1, ?, 'alpha', 1, 2, '2026-01-01 10:00:00', 2, 100.0, 1)
                    """,
                    (user_id,),
                )
                connection.executescript(
                    """
                    INSERT INTO quiz_answers (
                        id, attempt_id, question_id, selected_option_id, is_correct
                    )
                    VALUES
                        (1, 1, 'q1', 'a', 1),
                        (2, 1, 'q1', 'b', 1),
                        (3, 1, 'q2', 'a', 0);
                    """
                )

            initialize_database(db_path)

            with get_connection(db_path) as connection:
                rows = _answer_rows(connection)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["id"], 1)
                self.assertEqual(rows[1]["id"], 3)

                attempt = connection.execute(
                    """
                    SELECT correct_answers, score_percent, passed
                    FROM quiz_attempts
                    WHERE id = 1
                    """
                ).fetchone()
                self.assertEqual(attempt["correct_answers"], 1)
                self.assertEqual(attempt["score_percent"], 50.0)
                self.assertEqual(attempt["passed"], 1)

    def test_statistics_repair_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "stats-idempotent.db"
            with get_connection(db_path) as connection:
                connection.executescript(LEGACY_QUIZ_SCHEMA)
                user_id = connection.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (1001, "learner", "Test", "User"),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        id,
                        user_id,
                        course_slug,
                        quiz_version,
                        questions_count,
                        finished_at,
                        correct_answers,
                        score_percent
                    )
                    VALUES (1, ?, 'alpha', 1, 2, '2026-01-01 10:00:00', 3, 150.0)
                    """,
                    (user_id,),
                )
                connection.executescript(
                    """
                    INSERT INTO quiz_answers (
                        id, attempt_id, question_id, selected_option_id, is_correct
                    )
                    VALUES
                        (1, 1, 'q1', 'a', 1),
                        (2, 1, 'q1', 'b', 1),
                        (3, 1, 'q2', 'a', 0);
                    """
                )

            initialize_database(db_path)
            initialize_database(db_path)

            with get_connection(db_path) as connection:
                attempt = connection.execute(
                    """
                    SELECT correct_answers, score_percent
                    FROM quiz_attempts
                    WHERE id = 1
                    """
                ).fetchone()
                self.assertEqual(attempt["correct_answers"], 1)
                self.assertEqual(attempt["score_percent"], 50.0)

    def test_statistics_repair_runs_when_unique_index_already_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index-without-stats-repair.db"
            with get_connection(db_path) as connection:
                connection.executescript(LEGACY_QUIZ_SCHEMA)
                user_id = connection.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (1001, "learner", "Test", "User"),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        id,
                        user_id,
                        course_slug,
                        quiz_version,
                        questions_count,
                        finished_at,
                        correct_answers,
                        score_percent
                    )
                    VALUES (1, ?, 'alpha', 1, 6, '2026-01-01 10:00:00', 7, 116.67)
                    """,
                    (user_id,),
                )
                connection.executescript(
                    """
                    INSERT INTO quiz_answers (
                        id, attempt_id, question_id, selected_option_id, is_correct
                    )
                    VALUES
                        (1, 1, 'q1', 'a', 1),
                        (2, 1, 'q2', 'a', 1);
                    """
                )
                connection.execute(
                    """
                    CREATE UNIQUE INDEX idx_quiz_answers_attempt_question
                    ON quiz_answers(attempt_id, question_id)
                    """
                )

            initialize_database(db_path)

            with get_connection(db_path) as connection:
                attempt = connection.execute(
                    """
                    SELECT correct_answers, score_percent
                    FROM quiz_attempts
                    WHERE id = 1
                    """
                ).fetchone()
                self.assertEqual(attempt["correct_answers"], 2)
                self.assertEqual(attempt["score_percent"], 33.33)

    def test_initialize_database_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-idempotent.db"
            with get_connection(db_path) as connection:
                connection.executescript(LEGACY_QUIZ_SCHEMA)
                user_id = connection.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (1001, "learner", "Test", "User"),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO quiz_attempts (
                        id, user_id, course_slug, quiz_version, questions_count
                    )
                    VALUES (1, ?, 'alpha', 1, 2)
                    """,
                    (user_id,),
                )
                connection.executescript(
                    """
                    INSERT INTO quiz_answers (
                        id, attempt_id, question_id, selected_option_id, is_correct
                    )
                    VALUES
                        (1, 1, 'q1', 'a', 1),
                        (2, 1, 'q1', 'b', 0),
                        (3, 1, 'q2', 'a', 1);
                    """
                )

            initialize_database(db_path)
            initialize_database(db_path)

            with get_connection(db_path) as connection:
                rows = _answer_rows(connection)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["id"], 1)
                self.assertEqual(rows[1]["id"], 3)
                self.assertTrue(
                    _index_exists(
                        connection,
                        "idx_quiz_answers_attempt_question",
                    )
                )


if __name__ == "__main__":
    unittest.main()
