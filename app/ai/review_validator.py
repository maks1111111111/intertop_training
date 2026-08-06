"""Validate AI reviewer results for score and feedback quality.

Checks that parsed :class:`ReviewResult` values satisfy business rules
before persistence or downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.review_interfaces import ReviewResult

_PASS_THRESHOLD = 0.8


@dataclass(frozen=True)
class ReviewValidationReport:
    """Summary of AI review quality checks.

    Each counter reflects a single validation failure on the supplied
    :class:`ReviewResult`. ``valid`` is ``True`` only when every counter
    is zero.
    """

    negative_scores: int
    negative_max_scores: int
    scores_above_maximum: int
    invalid_passed_values: int
    empty_feedback_summaries: int
    empty_strengths: int
    empty_improvements: int
    valid: bool


class ReviewValidator:
    """Validate :class:`ReviewResult` for score and feedback quality."""

    def validate(self, result: ReviewResult) -> ReviewValidationReport:
        """Check score bounds, pass threshold, and feedback content.

        ``passed`` must match the 80% rule: when ``max_score`` is positive,
        ``score / max_score >= 0.8``; when ``max_score`` is zero, ``passed``
        must be ``False``. Empty ``feedback.summary`` after stripping and
        blank strength or improvement entries each count as failures.
        """
        negative_scores = 0
        negative_max_scores = 0
        scores_above_maximum = 0
        invalid_passed_values = 0
        empty_feedback_summaries = 0
        empty_strengths = 0
        empty_improvements = 0

        if result.score < 0:
            negative_scores = 1

        if result.max_score < 0:
            negative_max_scores = 1

        if result.score > result.max_score:
            scores_above_maximum = 1

        if result.max_score > 0:
            expected_passed = result.score / result.max_score >= _PASS_THRESHOLD
        else:
            expected_passed = False

        if result.passed != expected_passed:
            invalid_passed_values = 1

        if not result.feedback.summary.strip():
            empty_feedback_summaries = 1

        for strength in result.feedback.strengths:
            if not strength.strip():
                empty_strengths += 1

        for improvement in result.feedback.improvements:
            if not improvement.strip():
                empty_improvements += 1

        valid = (
            negative_scores == 0
            and negative_max_scores == 0
            and scores_above_maximum == 0
            and invalid_passed_values == 0
            and empty_feedback_summaries == 0
            and empty_strengths == 0
            and empty_improvements == 0
        )

        return ReviewValidationReport(
            negative_scores=negative_scores,
            negative_max_scores=negative_max_scores,
            scores_above_maximum=scores_above_maximum,
            invalid_passed_values=invalid_passed_values,
            empty_feedback_summaries=empty_feedback_summaries,
            empty_strengths=empty_strengths,
            empty_improvements=empty_improvements,
            valid=valid,
        )
