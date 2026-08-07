"""Tests for the practical-task review flow application service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ai.review_interfaces import ReviewFeedback, ReviewRequest, ReviewResult
from app.ai.review_service import PracticalTaskReviewService
from app.database.db import initialize_database, upsert_telegram_user
from app.repositories import practical_task_attempt_repository as repository
from app.services.practical_task_review_flow_service import (
    PracticalTaskAttemptCreationError,
    PracticalTaskReviewCompletionError,
    PracticalTaskReviewFlowService,
)


def _sample_request(
    *,
    lesson_title: str = "Safety Basics",
    practical_task_title: str = "Inspect the work area",
    practical_task_description: str = "Walk through the area and identify hazards.",
    expected_result: str = "All hazards are documented and addressed.",
    learner_answer: str = "I checked the floor and removed loose cables.",
) -> ReviewRequest:
    return ReviewRequest(
        lesson_title=lesson_title,
        practical_task_title=practical_task_title,
        practical_task_description=practical_task_description,
        expected_result=expected_result,
        learner_answer=learner_answer,
        criteria=(),
    )


def _sample_review_result(
    *,
    score: int = 8,
    max_score: int = 10,
    passed: bool = True,
    summary: str = "Good practical answer.",
    strengths: tuple[str, ...] = ("Identified hazards",),
    improvements: tuple[str, ...] = ("Add more detail",),
) -> ReviewResult:
    return ReviewResult(
        score=score,
        max_score=max_score,
        passed=passed,
        feedback=ReviewFeedback(
            summary=summary,
            strengths=strengths,
            improvements=improvements,
        ),
    )


class FakePracticalTaskReviewer:
    """Minimal test double that returns a fixed review result."""

    def __init__(self, result: ReviewResult) -> None:
        self._result = result
        self.last_request: ReviewRequest | None = None
        self.review_call_count = 0

    def review(self, request: ReviewRequest) -> ReviewResult:
        self.last_request = request
        self.review_call_count += 1
        return self._result


class PracticalTaskReviewFlowServiceTests(unittest.TestCase):
    """Integration-style tests with a real SQLite database."""

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
        self.course_slug = "safety"
        self.lesson_slug = "lesson_01"
        self.request = _sample_request()
        self.review_result = _sample_review_result()
        self.provider = FakePracticalTaskReviewer(self.review_result)
        self.service = PracticalTaskReviewFlowService(
            PracticalTaskReviewService(self.provider),
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_successful_workflow_creates_attempt(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        self.assertIsNotNone(attempt)

    def test_ai_receives_exact_review_request(self) -> None:
        self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        self.assertIs(self.provider.last_request, self.request)

    def test_task_snapshot_fields_are_saved(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(attempt.task_title, self.request.practical_task_title)
        self.assertEqual(attempt.task_description, self.request.practical_task_description)
        self.assertEqual(attempt.expected_result, self.request.expected_result)

    def test_learner_answer_is_saved(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(attempt.learner_answer, self.request.learner_answer)

    def test_successful_review_is_written_to_database(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(attempt.status, "reviewed")

    def test_score_max_score_and_passed_are_saved(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(attempt.score, self.review_result.score)
        self.assertEqual(attempt.max_score, self.review_result.max_score)
        self.assertEqual(attempt.passed, self.review_result.passed)

    def test_feedback_is_saved(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(attempt.feedback_summary, self.review_result.feedback.summary)
        self.assertEqual(attempt.strengths, self.review_result.feedback.strengths)
        self.assertEqual(attempt.improvements, self.review_result.feedback.improvements)
        self.assertIsNotNone(attempt.reviewed_at)

    def test_result_contains_correct_attempt_id(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(result.attempt_id, attempt.id)

    def test_result_contains_same_review_result(self) -> None:
        result = self.service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=self.request,
        )

        self.assertIs(result.review_result, self.review_result)

    def test_unicode_text_persists_end_to_end(self) -> None:
        request = _sample_request(
            practical_task_title="  Проверка рабочей зоны  ",
            practical_task_description="Описание на русском.",
            expected_result="Ожидаемый результат.",
            learner_answer="Ответ на казахском: қауіпсіздік.",
        )
        review_result = _sample_review_result(
            summary="Хороший ответ.",
            strengths=("Выявлены риски",),
            improvements=("Добавьте детали",),
        )
        provider = FakePracticalTaskReviewer(review_result)
        service = PracticalTaskReviewFlowService(
            PracticalTaskReviewService(provider),
        )

        result = service.submit_and_review(
            self.db_path,
            telegram_id=1001,
            course_slug=self.course_slug,
            lesson_slug=self.lesson_slug,
            request=request,
        )

        attempt = repository.get_attempt(self.db_path, result.attempt_id)
        assert attempt is not None
        self.assertEqual(attempt.task_title, "  Проверка рабочей зоны  ")
        self.assertEqual(attempt.learner_answer, "Ответ на казахском: қауіпсіздік.")
        self.assertEqual(attempt.feedback_summary, "Хороший ответ.")
        self.assertEqual(attempt.strengths, ("Выявлены риски",))


class PracticalTaskReviewFlowServiceErrorTests(unittest.TestCase):
    """Boundary-case tests for workflow error handling."""

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
        self.request = _sample_request()
        self.review_result = _sample_review_result()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_unknown_user_raises_controlled_error(self) -> None:
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)
        service = PracticalTaskReviewFlowService(mock_review_service)

        with self.assertRaises(PracticalTaskAttemptCreationError):
            service.submit_and_review(
                self.db_path,
                telegram_id=9999,
                course_slug="safety",
                lesson_slug="lesson_01",
                request=self.request,
            )

    def test_unknown_user_does_not_call_ai(self) -> None:
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)
        service = PracticalTaskReviewFlowService(mock_review_service)

        with self.assertRaises(PracticalTaskAttemptCreationError):
            service.submit_and_review(
                self.db_path,
                telegram_id=9999,
                course_slug="safety",
                lesson_slug="lesson_01",
                request=self.request,
            )

        mock_review_service.review.assert_not_called()

    def test_unknown_user_does_not_create_attempt(self) -> None:
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)
        service = PracticalTaskReviewFlowService(mock_review_service)

        with self.assertRaises(PracticalTaskAttemptCreationError):
            service.submit_and_review(
                self.db_path,
                telegram_id=9999,
                course_slug="safety",
                lesson_slug="lesson_01",
                request=self.request,
            )

        attempts = repository.get_attempts_for_lesson(
            self.db_path,
            telegram_id=9999,
            course_slug="safety",
            lesson_slug="lesson_01",
        )
        self.assertEqual(attempts, [])

    def test_ai_failure_propagates_exception(self) -> None:
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)
        mock_review_service.review.side_effect = RuntimeError("AI failed")
        service = PracticalTaskReviewFlowService(mock_review_service)

        with self.assertRaises(RuntimeError):
            service.submit_and_review(
                self.db_path,
                telegram_id=1001,
                course_slug="safety",
                lesson_slug="lesson_01",
                request=self.request,
            )

    def test_ai_failure_leaves_pending_attempt_in_database(self) -> None:
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)
        mock_review_service.review.side_effect = RuntimeError("AI failed")
        service = PracticalTaskReviewFlowService(mock_review_service)

        with self.assertRaises(RuntimeError):
            service.submit_and_review(
                self.db_path,
                telegram_id=1001,
                course_slug="safety",
                lesson_slug="lesson_01",
                request=self.request,
            )

        attempts = repository.get_attempts_for_lesson(
            self.db_path,
            telegram_id=1001,
            course_slug="safety",
            lesson_slug="lesson_01",
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, "pending")
        self.assertIsNone(attempts[0].score)
        self.assertIsNone(attempts[0].feedback_summary)

    @patch(
        "app.services.practical_task_review_flow_service"
        ".practical_task_attempt_repository.complete_review",
        return_value=False,
    )
    def test_persistence_failure_raises_completion_error_and_leaves_pending(
        self,
        mock_complete_review: MagicMock,
    ) -> None:
        provider = FakePracticalTaskReviewer(self.review_result)
        service = PracticalTaskReviewFlowService(
            PracticalTaskReviewService(provider),
        )

        with self.assertRaises(PracticalTaskReviewCompletionError):
            service.submit_and_review(
                self.db_path,
                telegram_id=1001,
                course_slug="safety",
                lesson_slug="lesson_01",
                request=self.request,
            )

        self.assertEqual(provider.review_call_count, 1)
        mock_complete_review.assert_called_once()

        attempts = repository.get_attempts_for_lesson(
            self.db_path,
            telegram_id=1001,
            course_slug="safety",
            lesson_slug="lesson_01",
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, "pending")
        self.assertIsNone(attempts[0].score)
        self.assertIsNone(attempts[0].feedback_summary)


if __name__ == "__main__":
    unittest.main()
