"""Parse AI model responses into structured review results."""

from __future__ import annotations

import json
from typing import Any, Tuple

from app.ai.review_interfaces import ReviewFeedback, ReviewResult


class ReviewResponseParser:
    """Convert raw AI text responses into :class:`ReviewResult`."""

    def parse(self, response: str) -> ReviewResult:
        """Parse model output into a review result.

        Args:
            response: Raw JSON text from the AI model.

        Returns:
            Parsed :class:`ReviewResult`.

        Raises:
            json.JSONDecodeError: If the response is not valid JSON.
            ValueError: If the JSON structure or field types are invalid.
        """
        data = json.loads(response)
        if not isinstance(data, dict):
            raise ValueError("Review response root must be a JSON object.")

        score = _parse_score(data)
        max_score = _parse_max_score(data)
        passed = _parse_passed(data)
        feedback = _parse_feedback(data)

        return ReviewResult(
            score=score,
            max_score=max_score,
            passed=passed,
            feedback=feedback,
        )


def _parse_score(data: dict[str, Any]) -> int:
    if "score" not in data:
        raise ValueError("Field 'score' is required.")

    score = data["score"]
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("Field 'score' must be an integer.")

    return score


def _parse_max_score(data: dict[str, Any]) -> int:
    if "max_score" not in data:
        raise ValueError("Field 'max_score' is required.")

    max_score = data["max_score"]
    if isinstance(max_score, bool) or not isinstance(max_score, int):
        raise ValueError("Field 'max_score' must be an integer.")

    return max_score


def _parse_passed(data: dict[str, Any]) -> bool:
    if "passed" not in data:
        raise ValueError("Field 'passed' is required.")

    passed = data["passed"]
    if not isinstance(passed, bool):
        raise ValueError("Field 'passed' must be a boolean.")

    return passed


def _parse_feedback(data: dict[str, Any]) -> ReviewFeedback:
    if "feedback" not in data:
        raise ValueError("Field 'feedback' is required.")

    feedback = data["feedback"]
    if not isinstance(feedback, dict):
        raise ValueError("Field 'feedback' must be a JSON object.")

    summary = _parse_feedback_summary(feedback)
    strengths = _parse_string_list(feedback, "strengths", "feedback.strengths")
    improvements = _parse_string_list(
        feedback,
        "improvements",
        "feedback.improvements",
    )

    return ReviewFeedback(
        summary=summary,
        strengths=strengths,
        improvements=improvements,
    )


def _parse_feedback_summary(feedback: dict[str, Any]) -> str:
    if "summary" not in feedback:
        raise ValueError("Field 'feedback.summary' is required.")

    summary = feedback["summary"]
    if not isinstance(summary, str):
        raise ValueError("Field 'feedback.summary' must be a string.")

    return summary


def _parse_string_list(
    feedback: dict[str, Any],
    field_name: str,
    location: str,
) -> Tuple[str, ...]:
    if field_name not in feedback:
        raise ValueError(f"Field '{location}' is required.")

    values = feedback[field_name]
    if not isinstance(values, list):
        raise ValueError(f"Field '{location}' must be a list.")

    result: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str):
            raise ValueError(
                f"Field '{location}' item at index {index} must be a string."
            )
        result.append(item)

    return tuple(result)
