"""Tests for AI review validator (``app.ai.review_validator``)."""

from __future__ import annotations

import unittest
from typing import Optional, Tuple

from app.ai.review_interfaces import ReviewFeedback, ReviewResult
from app.ai.review_validator import ReviewValidationReport, ReviewValidator


def _valid_feedback(
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


def _valid_result(
    score: int = 8,
    max_score: int = 10,
    passed: bool = True,
    feedback: Optional[ReviewFeedback] = None,
) -> ReviewResult:
    if feedback is None:
        feedback = _valid_feedback()
    return ReviewResult(
        score=score,
        max_score=max_score,
        passed=passed,
        feedback=feedback,
    )


def _zero_counters() -> dict[str, int]:
    return {
        "negative_scores": 0,
        "negative_max_scores": 0,
        "scores_above_maximum": 0,
        "invalid_passed_values": 0,
        "empty_feedback_summaries": 0,
        "empty_strengths": 0,
        "empty_improvements": 0,
    }


class ReviewValidatorTests(unittest.TestCase):
    """Tests for :class:`ReviewValidator`."""

    def setUp(self) -> None:
        self.validator = ReviewValidator()

    def test_fully_valid_result(self) -> None:
        report = self.validator.validate(_valid_result())

        self.assertEqual(
            report,
            ReviewValidationReport(valid=True, **_zero_counters()),
        )

    def test_score_zero_max_ten_passed_false_is_valid(self) -> None:
        report = self.validator.validate(
            _valid_result(score=0, max_score=10, passed=False)
        )

        self.assertTrue(report.valid)
        self.assertEqual(report, ReviewValidationReport(valid=True, **_zero_counters()))

    def test_negative_score(self) -> None:
        report = self.validator.validate(
            _valid_result(score=-1, max_score=10, passed=False)
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.negative_scores, 1)
        self.assertEqual(report.negative_max_scores, 0)
        self.assertEqual(report.scores_above_maximum, 0)
        self.assertEqual(report.invalid_passed_values, 0)

    def test_negative_max_score(self) -> None:
        report = self.validator.validate(_valid_result(max_score=-1))

        self.assertFalse(report.valid)
        self.assertEqual(report.negative_max_scores, 1)
        self.assertEqual(report.negative_scores, 0)

    def test_score_above_maximum(self) -> None:
        report = self.validator.validate(_valid_result(score=11, max_score=10))

        self.assertFalse(report.valid)
        self.assertEqual(report.scores_above_maximum, 1)

    def test_passed_true_below_eighty_percent(self) -> None:
        report = self.validator.validate(
            _valid_result(score=7, max_score=10, passed=True)
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.invalid_passed_values, 1)

    def test_passed_false_at_or_above_eighty_percent(self) -> None:
        report = self.validator.validate(
            _valid_result(score=8, max_score=10, passed=False)
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.invalid_passed_values, 1)

    def test_exactly_eighty_percent_with_passed_true(self) -> None:
        report = self.validator.validate(
            _valid_result(score=8, max_score=10, passed=True)
        )

        self.assertTrue(report.valid)
        self.assertEqual(report.invalid_passed_values, 0)

    def test_zero_max_score_zero_score_passed_false(self) -> None:
        report = self.validator.validate(
            _valid_result(score=0, max_score=0, passed=False)
        )

        self.assertTrue(report.valid)
        self.assertEqual(report, ReviewValidationReport(valid=True, **_zero_counters()))

    def test_zero_max_score_zero_score_passed_true(self) -> None:
        report = self.validator.validate(
            _valid_result(score=0, max_score=0, passed=True)
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.invalid_passed_values, 1)

    def test_empty_feedback_summary(self) -> None:
        report = self.validator.validate(
            _valid_result(feedback=_valid_feedback(summary=""))
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.empty_feedback_summaries, 1)

    def test_whitespace_only_feedback_summary(self) -> None:
        report = self.validator.validate(
            _valid_result(feedback=_valid_feedback(summary="   "))
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.empty_feedback_summaries, 1)

    def test_empty_strength_elements_counted_separately(self) -> None:
        report = self.validator.validate(
            _valid_result(
                feedback=_valid_feedback(
                    strengths=("", "ok", "   "),
                )
            )
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.empty_strengths, 2)
        self.assertEqual(report.empty_improvements, 0)

    def test_empty_improvement_elements_counted_separately(self) -> None:
        report = self.validator.validate(
            _valid_result(
                feedback=_valid_feedback(
                    improvements=(" ", "Valid improvement", ""),
                )
            )
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.empty_improvements, 2)
        self.assertEqual(report.empty_strengths, 0)

    def test_empty_strengths_and_improvements_tuples_are_valid(self) -> None:
        report = self.validator.validate(
            _valid_result(
                feedback=_valid_feedback(
                    strengths=(),
                    improvements=(),
                )
            )
        )

        self.assertTrue(report.valid)
        self.assertEqual(report.empty_strengths, 0)
        self.assertEqual(report.empty_improvements, 0)

    def test_multiple_errors_increment_all_counters(self) -> None:
        report = self.validator.validate(
            ReviewResult(
                score=-2,
                max_score=-3,
                passed=True,
                feedback=ReviewFeedback(
                    summary="",
                    strengths=("",),
                    improvements=("  ",),
                ),
            )
        )

        self.assertFalse(report.valid)
        self.assertEqual(report.negative_scores, 1)
        self.assertEqual(report.negative_max_scores, 1)
        self.assertEqual(report.scores_above_maximum, 1)
        self.assertEqual(report.invalid_passed_values, 1)
        self.assertEqual(report.empty_feedback_summaries, 1)
        self.assertEqual(report.empty_strengths, 1)
        self.assertEqual(report.empty_improvements, 1)

    def test_validator_does_not_mutate_result(self) -> None:
        original = _valid_result(
            score=8,
            max_score=10,
            passed=True,
            feedback=_valid_feedback(
                summary="Original summary.",
                strengths=("Strength one",),
                improvements=("Improvement one",),
            ),
        )
        snapshot = ReviewResult(
            score=original.score,
            max_score=original.max_score,
            passed=original.passed,
            feedback=ReviewFeedback(
                summary=original.feedback.summary,
                strengths=original.feedback.strengths,
                improvements=original.feedback.improvements,
            ),
        )

        self.validator.validate(original)

        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main()
