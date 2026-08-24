"""Tests for canonical-user Web practical task service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.ai.review_interfaces import ReviewFeedback, ReviewResult
from app.content.practical_task import PracticalTask
from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories import practical_task_attempt_repository
from app.web.web_practical_task_service import (
    WebPracticalTaskNotFoundError,
    WebPracticalTaskReviewUnavailableError,
    WebPracticalTaskService,
    WebPracticalTaskValidationError,
)


class FakeReviewer:
    def __init__(self) -> None:
        self.calls = 0
        self.last_request = None

    def review(self, request):
        self.calls += 1
        self.last_request = request
        return ReviewResult(
            score=8,
            max_score=10,
            passed=True,
            feedback=ReviewFeedback(
                summary="Хороший ответ.",
                strengths=("Верная последовательность",),
                improvements=("Добавьте детали",),
            ),
        )


class WebPracticalTaskServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        initialize_database(self.db_path)

        upsert_telegram_user(
            self.db_path,
            telegram_id=7001,
            username="web-user",
            first_name="Web",
            last_name="Learner",
        )
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (7001,),
            ).fetchone()
            assert row is not None
            self.user_id = int(row["id"])
            connection.execute(
                "UPDATE users SET telegram_id = NULL WHERE id = ?",
                (self.user_id,),
            )

        task = PracticalTask(
            title="Проверка рабочей зоны",
            description="Осмотрите рабочую зону и опишите риски.",
            expected_result="Все риски выявлены и описаны.",
        )
        self.lesson = SimpleNamespace(
            title="Безопасность",
            path=Path("lesson_01"),
            structured_practical_task=task,
        )
        self.course = SimpleNamespace(
            slug="safety",
            language="ru",
            lessons=[self.lesson],
        )

        self.runtime = MagicMock()
        self.runtime.get_course.side_effect = (
            lambda slug: self.course if slug == "safety" else None
        )

        self.reviewer = FakeReviewer()
        self.service = WebPracticalTaskService(
            self.runtime,
            self.reviewer,
            self.db_path,
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_submit_creates_reviewed_canonical_attempt(self) -> None:
        result = self.service.submit_and_review(
            self.user_id,
            "safety",
            "lesson_01",
            "  Я осмотрел рабочую зону.  ",
        )

        attempt = practical_task_attempt_repository.get_attempt(
            self.db_path,
            result.attempt_id,
        )
        assert attempt is not None

        self.assertEqual(attempt.user_id, self.user_id)
        self.assertIsNone(attempt.telegram_id)
        self.assertEqual(attempt.learner_answer, "Я осмотрел рабочую зону.")
        self.assertEqual(attempt.status, "reviewed")
        self.assertEqual(attempt.score, 8)
        self.assertTrue(attempt.passed)
        self.assertEqual(self.reviewer.last_request.language, "ru")

    def test_invalid_and_missing_submission_skip_ai(self) -> None:
        with self.assertRaises(WebPracticalTaskValidationError):
            self.service.submit_and_review(
                self.user_id, "safety", "lesson_01", "   "
            )

        with self.assertRaises(WebPracticalTaskNotFoundError):
            self.service.submit_and_review(
                self.user_id, "missing", "lesson_01", "Ответ"
            )

        self.assertEqual(self.reviewer.calls, 0)

    def test_ai_failure_leaves_pending_attempt(self) -> None:
        reviewer = MagicMock()
        reviewer.review.side_effect = RuntimeError("AI failed")
        service = WebPracticalTaskService(
            self.runtime,
            reviewer,
            self.db_path,
        )

        with self.assertRaises(RuntimeError):
            service.submit_and_review(
                self.user_id, "safety", "lesson_01", "Ответ"
            )

        attempts = (
            practical_task_attempt_repository.get_attempts_for_lesson_for_user(
                self.db_path,
                self.user_id,
                "safety",
                "lesson_01",
            )
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, "pending")

    def test_missing_ai_review_service_is_controlled(self) -> None:
        service = WebPracticalTaskService(
            self.runtime,
            None,
            self.db_path,
        )

        with self.assertRaises(WebPracticalTaskReviewUnavailableError):
            service.submit_and_review(
                self.user_id,
                "safety",
                "lesson_01",
                "Ответ",
            )

        attempts = practical_task_attempt_repository.get_attempts_for_lesson_for_user(
            self.db_path,
            self.user_id,
            "safety",
            "lesson_01",
        )
        self.assertEqual(attempts, [])


if __name__ == "__main__":
    unittest.main()
