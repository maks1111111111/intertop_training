"""Tests for canonical-user quiz repository access."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories import quiz_repository


class CanonicalUserQuizRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            self.user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name
                    )
                    VALUES (NULL, ?, ?, ?)
                    """,
                    ("web-only", "Web", "Only"),
                ).lastrowid
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_attempt(
        self,
        *,
        course_slug: str = "alpha",
        questions_count: int = 2,
    ) -> int:
        attempt_id = quiz_repository.create_attempt_for_user(
            self.db_path,
            user_id=self.user_id,
            course_slug=course_slug,
            quiz_version=1,
            questions_count=questions_count,
        )
        self.assertIsNotNone(attempt_id)
        return int(attempt_id)

    def test_password_only_user_can_create_attempt(self) -> None:
        attempt_id = self._create_attempt()

        attempt = quiz_repository.get_attempt(self.db_path, attempt_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(int(attempt["user_id"]), self.user_id)

    def test_active_attempt_is_reused(self) -> None:
        first = self._create_attempt()
        second = self._create_attempt()

        self.assertEqual(first, second)

    def test_unknown_user_does_not_create_attempt(self) -> None:
        attempt_id = quiz_repository.create_attempt_for_user(
            self.db_path,
            user_id=999999,
            course_slug="alpha",
            quiz_version=1,
            questions_count=2,
        )

        self.assertIsNone(attempt_id)

    def test_get_active_attempt_for_password_only_user(self) -> None:
        attempt_id = self._create_attempt()

        active = quiz_repository.get_active_attempt_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(int(active["id"]), attempt_id)

    def test_finished_attempt_no_longer_active(self) -> None:
        attempt_id = self._create_attempt()

        quiz_repository.save_answer(
            self.db_path,
            attempt_id,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            self.db_path,
            attempt_id,
            question_id="q2",
            selected_option_id="b",
            is_correct=False,
        )
        quiz_repository.finish_attempt(self.db_path, attempt_id)

        self.assertIsNone(
            quiz_repository.get_active_attempt_for_user(
                self.db_path,
                self.user_id,
                "alpha",
            )
        )

    def test_finished_attempts_work_without_telegram_id(self) -> None:
        attempt_id = self._create_attempt()

        quiz_repository.save_answer(
            self.db_path,
            attempt_id,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.finish_attempt(self.db_path, attempt_id)

        attempts = quiz_repository.get_finished_attempts_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(int(attempts[0]["id"]), attempt_id)

    def test_course_stats_work_without_telegram_id(self) -> None:
        first = self._create_attempt()

        quiz_repository.save_answer(
            self.db_path,
            first,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            self.db_path,
            first,
            question_id="q2",
            selected_option_id="b",
            is_correct=False,
        )
        quiz_repository.finish_attempt(self.db_path, first)

        second = self._create_attempt()

        quiz_repository.save_answer(
            self.db_path,
            second,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            self.db_path,
            second,
            question_id="q2",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.finish_attempt(self.db_path, second)

        stats = quiz_repository.get_course_quiz_stats_for_user(
            self.db_path,
            self.user_id,
            "alpha",
        )

        self.assertEqual(stats["attempts_count"], 2)
        self.assertEqual(stats["best_score_percent"], 100.0)
        self.assertEqual(stats["average_score_percent"], 75.0)
        self.assertEqual(stats["latest_score_percent"], 100.0)
        self.assertTrue(stats["latest_passed"])
        self.assertTrue(stats["ever_passed"])

    def test_empty_stats_are_returned_for_not_started_course(self) -> None:
        stats = quiz_repository.get_course_quiz_stats_for_user(
            self.db_path,
            self.user_id,
            "missing-course",
        )

        self.assertEqual(stats["attempts_count"], 0)
        self.assertIsNone(stats["best_score_percent"])
        self.assertIsNone(stats["average_score_percent"])
        self.assertIsNone(stats["latest_score_percent"])
        self.assertFalse(stats["latest_passed"])
        self.assertFalse(stats["ever_passed"])

    def test_finished_attempt_limit_is_respected(self) -> None:
        first = self._create_attempt()
        quiz_repository.save_answer(
            self.db_path,
            first,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.finish_attempt(self.db_path, first)

        second = self._create_attempt()
        quiz_repository.save_answer(
            self.db_path,
            second,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.finish_attempt(self.db_path, second)

        attempts = quiz_repository.get_finished_attempts_for_user(
            self.db_path,
            self.user_id,
            "alpha",
            limit=1,
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(int(attempts[0]["id"]), second)

    def test_non_positive_limit_returns_empty(self) -> None:
        self.assertEqual(
            quiz_repository.get_finished_attempts_for_user(
                self.db_path,
                self.user_id,
                "alpha",
                limit=0,
            ),
            [],
        )

    def test_invalid_user_ids_are_rejected(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    quiz_repository.get_course_quiz_stats_for_user(
                        self.db_path,
                        invalid,  # type: ignore[arg-type]
                        "alpha",
                    )


if __name__ == "__main__":
    unittest.main()
