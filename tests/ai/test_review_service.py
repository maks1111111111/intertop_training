"""Tests for :mod:`app.ai.review_service`."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.review_interfaces import (
    PracticalTaskReviewerAI,
    ReviewFeedback,
    ReviewRequest,
    ReviewResult,
)
from app.ai.review_service import PracticalTaskReviewService


def _sample_request() -> ReviewRequest:
    return ReviewRequest(
        lesson_title="Safety Basics",
        practical_task_title="Inspect the work area",
        practical_task_description="Walk through the area and identify hazards.",
        expected_result="All hazards are documented and addressed.",
        learner_answer="I checked the floor and removed loose cables.",
        criteria=(),
    )


def _sample_result() -> ReviewResult:
    return ReviewResult(
        score=8,
        max_score=10,
        passed=True,
        feedback=ReviewFeedback(
            summary="Strong answer with minor gaps.",
            strengths=("Identified hazards.",),
            improvements=("Document corrective actions.",),
        ),
    )


class PracticalTaskReviewServiceTests(unittest.TestCase):
    """Tests for :class:`PracticalTaskReviewService`."""

    def test_review_calls_provider_once(self) -> None:
        provider = MagicMock(spec=PracticalTaskReviewerAI)
        provider.review.return_value = _sample_result()
        service = PracticalTaskReviewService(provider)
        request = _sample_request()

        service.review(request)

        provider.review.assert_called_once_with(request)

    def test_review_passes_same_request_object(self) -> None:
        provider = MagicMock(spec=PracticalTaskReviewerAI)
        provider.review.return_value = _sample_result()
        service = PracticalTaskReviewService(provider)
        request = _sample_request()

        service.review(request)

        passed_request = provider.review.call_args[0][0]
        self.assertIs(passed_request, request)

    def test_review_returns_provider_result(self) -> None:
        provider = MagicMock(spec=PracticalTaskReviewerAI)
        expected_result = _sample_result()
        provider.review.return_value = expected_result
        service = PracticalTaskReviewService(provider)

        result = service.review(_sample_request())

        self.assertIs(result, expected_result)

    def test_provider_exception_propagates(self) -> None:
        provider = MagicMock(spec=PracticalTaskReviewerAI)
        provider.review.side_effect = RuntimeError("AI provider failed.")
        service = PracticalTaskReviewService(provider)

        with self.assertRaises(RuntimeError) as context:
            service.review(_sample_request())

        self.assertEqual(str(context.exception), "AI provider failed.")

    def test_provider_is_stored(self) -> None:
        provider = MagicMock(spec=PracticalTaskReviewerAI)

        service = PracticalTaskReviewService(provider)

        self.assertIs(service._provider, provider)
