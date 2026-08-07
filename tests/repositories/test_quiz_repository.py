"""Tests for quiz_repository answer persistence."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories import quiz_repository


class QuizRepositorySaveAnswerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        upsert_telegram_user(
            self.db_path,
            telegram_id=1001,
            username="learner",
            first_name="Test",
            last_name="User",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_attempt(
        self,
        *,
        telegram_id: int = 1001,
        course_slug: str = "alpha",
        questions_count: int = 6,
    ) -> int:
        attempt_id = quiz_repository.create_attempt(
            self.db_path,
            telegram_id=telegram_id,
            course_slug=course_slug,
            quiz_version=1,
            questions_count=questions_count,
        )
        self.assertIsNotNone(attempt_id)
        return int(attempt_id)

    def _answer_rows(self, attempt_id: int) -> list[sqlite3.Row]:
        with get_connection(self.db_path) as connection:
            return connection.execute(
                """
                SELECT *
                FROM quiz_answers
                WHERE attempt_id = ?
                ORDER BY id
                """,
                (attempt_id,),
            ).fetchall()

    def test_first_save_answer_returns_true(self) -> None:
        attempt_id = self._create_attempt()

        saved = quiz_repository.save_answer(
            self.db_path,
            attempt_id=attempt_id,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )

        self.assertTrue(saved)
        self.assertEqual(len(self._answer_rows(attempt_id)), 1)

    def test_repeat_same_question_returns_false(self) -> None:
        attempt_id = self._create_attempt()

        self.assertTrue(
            quiz_repository.save_answer(
                self.db_path,
                attempt_id=attempt_id,
                question_id="q1",
                selected_option_id="a",
                is_correct=True,
            )
        )
        saved = quiz_repository.save_answer(
            self.db_path,
            attempt_id=attempt_id,
            question_id="q1",
            selected_option_id="b",
            is_correct=False,
        )

        self.assertFalse(saved)
        self.assertEqual(len(self._answer_rows(attempt_id)), 1)

    def test_repeat_does_not_change_selected_option_id(self) -> None:
        attempt_id = self._create_attempt()

        quiz_repository.save_answer(
            self.db_path,
            attempt_id=attempt_id,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            self.db_path,
            attempt_id=attempt_id,
            question_id="q1",
            selected_option_id="b",
            is_correct=True,
        )

        row = self._answer_rows(attempt_id)[0]
        self.assertEqual(row["selected_option_id"], "a")
        self.assertEqual(row["is_correct"], 1)

    def test_different_questions_in_same_attempt_are_saved(self) -> None:
        attempt_id = self._create_attempt()

        self.assertTrue(
            quiz_repository.save_answer(
                self.db_path,
                attempt_id=attempt_id,
                question_id="q1",
                selected_option_id="a",
                is_correct=True,
            )
        )
        self.assertTrue(
            quiz_repository.save_answer(
                self.db_path,
                attempt_id=attempt_id,
                question_id="q2",
                selected_option_id="b",
                is_correct=False,
            )
        )

        self.assertEqual(len(self._answer_rows(attempt_id)), 2)

    def test_same_question_in_different_attempts_is_allowed(self) -> None:
        first_attempt_id = self._create_attempt(course_slug="alpha")
        second_attempt_id = self._create_attempt(course_slug="beta")

        self.assertTrue(
            quiz_repository.save_answer(
                self.db_path,
                attempt_id=first_attempt_id,
                question_id="q1",
                selected_option_id="a",
                is_correct=True,
            )
        )
        self.assertTrue(
            quiz_repository.save_answer(
                self.db_path,
                attempt_id=second_attempt_id,
                question_id="q1",
                selected_option_id="b",
                is_correct=False,
            )
        )

        self.assertEqual(len(self._answer_rows(first_attempt_id)), 1)
        self.assertEqual(len(self._answer_rows(second_attempt_id)), 1)

    def test_database_rejects_duplicate_answer_rows(self) -> None:
        attempt_id = self._create_attempt()

        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO quiz_answers (
                    attempt_id,
                    question_id,
                    selected_option_id,
                    is_correct
                )
                VALUES (?, ?, ?, ?)
                """,
                (attempt_id, "q1", "a", 1),
            )

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO quiz_answers (
                        attempt_id,
                        question_id,
                        selected_option_id,
                        is_correct
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (attempt_id, "q1", "b", 1),
                )

    def test_save_answer_with_unknown_attempt_raises_integrity_error(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            quiz_repository.save_answer(
                self.db_path,
                attempt_id=999999,
                question_id="q1",
                selected_option_id="a",
                is_correct=True,
            )

    def test_finish_attempt_never_exceeds_questions_count(self) -> None:
        db_path = Path(self._tmpdir.name) / "legacy-corrupt.db"
        with get_connection(db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                """
            )
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
                    questions_count
                )
                VALUES (1, ?, 'alpha', 1, 1)
                """,
                (user_id,),
            )
            connection.execute(
                """
                INSERT INTO quiz_answers (
                    id, attempt_id, question_id, selected_option_id, is_correct
                )
                VALUES (1, 1, 'q1', 'a', 1)
                """
            )
            connection.execute(
                """
                INSERT INTO quiz_answers (
                    id, attempt_id, question_id, selected_option_id, is_correct
                )
                VALUES (2, 1, 'q1', 'b', 1)
                """
            )

        quiz_repository.finish_attempt(db_path, attempt_id=1)

        attempt = quiz_repository.get_attempt(db_path, 1)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt["questions_count"], 1)
        self.assertEqual(attempt["correct_answers"], 1)
        self.assertLessEqual(float(attempt["score_percent"]), 100.0)


if __name__ == "__main__":
    unittest.main()
