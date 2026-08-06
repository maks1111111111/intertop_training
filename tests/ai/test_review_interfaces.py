"""Tests for AI reviewer data contracts (``app.ai.review_interfaces``)."""

from __future__ import annotations

import unittest
from typing import Optional, Tuple

from app.ai.review_interfaces import (
    ReviewCriterion,
    ReviewFeedback,
    ReviewRequest,
    ReviewResult,
)


def _sample_criterion(
    criterion_id: str = "completeness",
    title: str = "Completeness",
    description: str = "The answer covers all required steps.",
    max_score: int = 5,
) -> ReviewCriterion:
    return ReviewCriterion(
        id=criterion_id,
        title=title,
        description=description,
        max_score=max_score,
    )


def _sample_feedback(
    summary: str = "Good attempt with room for improvement.",
    strengths: Optional[Tuple[str, ...]] = None,
    improvements: Optional[Tuple[str, ...]] = None,
) -> ReviewFeedback:
    if strengths is None:
        strengths = ("Identified key hazards.",)
    if improvements is None:
        improvements = ("Add more detail about corrective actions.",)
    return ReviewFeedback(
        summary=summary,
        strengths=strengths,
        improvements=improvements,
    )


class ReviewCriterionTests(unittest.TestCase):
    """Tests for :class:`ReviewCriterion`."""

    def test_create_criterion(self) -> None:
        criterion = _sample_criterion()

        self.assertEqual(criterion.id, "completeness")
        self.assertEqual(criterion.title, "Completeness")
        self.assertEqual(criterion.description, "The answer covers all required steps.")
        self.assertEqual(criterion.max_score, 5)

    def test_equality(self) -> None:
        left = _sample_criterion()
        right = _sample_criterion()

        self.assertEqual(left, right)

    def test_immutable(self) -> None:
        criterion = _sample_criterion()

        with self.assertRaises(AttributeError):
            criterion.max_score = 10  # type: ignore[misc]


class ReviewFeedbackTests(unittest.TestCase):
    """Tests for :class:`ReviewFeedback`."""

    def test_create_feedback(self) -> None:
        feedback = _sample_feedback()

        self.assertEqual(feedback.summary, "Good attempt with room for improvement.")
        self.assertEqual(feedback.strengths, ("Identified key hazards.",))
        self.assertEqual(
            feedback.improvements,
            ("Add more detail about corrective actions.",),
        )

    def test_empty_tuples_allowed(self) -> None:
        feedback = ReviewFeedback(
            summary="No strengths or improvements recorded.",
            strengths=(),
            improvements=(),
        )

        self.assertEqual(feedback.strengths, ())
        self.assertEqual(feedback.improvements, ())
        self.assertIsInstance(feedback.strengths, tuple)
        self.assertIsInstance(feedback.improvements, tuple)

    def test_tuple_usage(self) -> None:
        feedback = _sample_feedback(
            strengths=("First strength.", "Second strength."),
            improvements=("First improvement.",),
        )

        self.assertIsInstance(feedback.strengths, tuple)
        self.assertIsInstance(feedback.improvements, tuple)
        self.assertEqual(len(feedback.strengths), 2)
        self.assertEqual(len(feedback.improvements), 1)


class ReviewResultTests(unittest.TestCase):
    """Tests for :class:`ReviewResult`."""

    def test_create_result(self) -> None:
        feedback = _sample_feedback()
        result = ReviewResult(
            score=4,
            max_score=5,
            passed=True,
            feedback=feedback,
        )

        self.assertEqual(result.score, 4)
        self.assertEqual(result.max_score, 5)
        self.assertTrue(result.passed)
        self.assertEqual(result.feedback, feedback)

    def test_score_can_be_zero(self) -> None:
        result = ReviewResult(
            score=0,
            max_score=5,
            passed=False,
            feedback=_sample_feedback(summary="Answer needs significant work."),
        )

        self.assertEqual(result.score, 0)

    def test_max_score_can_be_greater_than_score(self) -> None:
        result = ReviewResult(
            score=3,
            max_score=10,
            passed=False,
            feedback=_sample_feedback(),
        )

        self.assertLess(result.score, result.max_score)

    def test_passed_can_be_true(self) -> None:
        result = ReviewResult(
            score=5,
            max_score=5,
            passed=True,
            feedback=_sample_feedback(),
        )

        self.assertTrue(result.passed)

    def test_passed_can_be_false(self) -> None:
        result = ReviewResult(
            score=2,
            max_score=5,
            passed=False,
            feedback=_sample_feedback(),
        )

        self.assertFalse(result.passed)


class ReviewRequestTests(unittest.TestCase):
    """Tests for :class:`ReviewRequest`."""

    def test_create_request(self) -> None:
        criteria = (
            _sample_criterion("completeness", max_score=5),
            _sample_criterion("accuracy", title="Accuracy", max_score=5),
        )
        request = ReviewRequest(
            lesson_title="Safety Basics",
            practical_task_title="Inspect the work area",
            practical_task_description="Walk through the area and identify hazards.",
            expected_result="All hazards are documented and addressed.",
            learner_answer="I checked the floor and removed loose cables.",
            criteria=criteria,
        )

        self.assertEqual(request.lesson_title, "Safety Basics")
        self.assertEqual(request.practical_task_title, "Inspect the work area")
        self.assertEqual(
            request.practical_task_description,
            "Walk through the area and identify hazards.",
        )
        self.assertEqual(
            request.expected_result,
            "All hazards are documented and addressed.",
        )
        self.assertEqual(
            request.learner_answer,
            "I checked the floor and removed loose cables.",
        )
        self.assertEqual(request.criteria, criteria)

    def test_tuple_usage_for_criteria(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson 1",
            practical_task_title="Task",
            practical_task_description="Do the task.",
            expected_result="Task completed.",
            learner_answer="Done.",
            criteria=(_sample_criterion(),),
        )

        self.assertIsInstance(request.criteria, tuple)
        self.assertEqual(len(request.criteria), 1)
        self.assertTrue(
            all(isinstance(criterion, ReviewCriterion) for criterion in request.criteria)
        )

    def test_empty_criteria_tuple_allowed(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson 1",
            practical_task_title="Task",
            practical_task_description="Do the task.",
            expected_result="Task completed.",
            learner_answer="Done.",
            criteria=(),
        )

        self.assertEqual(request.criteria, ())
        self.assertIsInstance(request.criteria, tuple)
