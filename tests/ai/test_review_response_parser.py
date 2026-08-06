"""Tests for AI review response parser (``app.ai.review_response_parser``)."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional

from app.ai.review_interfaces import ReviewFeedback, ReviewResult
from app.ai.review_response_parser import ReviewResponseParser


_DEFAULT_FEEDBACK: Dict[str, Any] = {
    "summary": "Good answer with clear steps.",
    "strengths": ["Identified key hazards."],
    "improvements": ["Add corrective actions."],
}


def _valid_review_payload(
    score: int = 8,
    max_score: int = 10,
    passed: bool = True,
    feedback: Any = _DEFAULT_FEEDBACK,
    extra_root: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if feedback is _DEFAULT_FEEDBACK:
        feedback = dict(_DEFAULT_FEEDBACK)
    payload: Dict[str, Any] = {
        "score": score,
        "max_score": max_score,
        "passed": passed,
        "feedback": feedback,
    }
    if extra_root:
        payload.update(extra_root)
    return payload


class ReviewResponseParserSuccessTests(unittest.TestCase):
    """Tests for successful review parsing."""

    def setUp(self) -> None:
        self.parser = ReviewResponseParser()

    def test_parse_full_valid_json(self) -> None:
        response = json.dumps(_valid_review_payload())

        result = self.parser.parse(response)

        self.assertIsInstance(result, ReviewResult)
        self.assertEqual(result.score, 8)
        self.assertEqual(result.max_score, 10)
        self.assertTrue(result.passed)
        self.assertIsInstance(result.feedback, ReviewFeedback)
        self.assertEqual(result.feedback.summary, "Good answer with clear steps.")
        self.assertEqual(result.feedback.strengths, ("Identified key hazards.",))
        self.assertEqual(
            result.feedback.improvements,
            ("Add corrective actions.",),
        )

    def test_empty_strengths_and_improvements(self) -> None:
        payload = _valid_review_payload(
            feedback={
                "summary": "Minimal feedback.",
                "strengths": [],
                "improvements": [],
            }
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.feedback.strengths, ())
        self.assertEqual(result.feedback.improvements, ())
        self.assertIsInstance(result.feedback.strengths, tuple)
        self.assertIsInstance(result.feedback.improvements, tuple)

    def test_strings_preserved_without_normalization(self) -> None:
        payload = _valid_review_payload(
            feedback={
                "summary": "  Summary with spaces.\n",
                "strengths": ["  Leading spaces", "Trailing spaces  "],
                "improvements": ["Line one.\nLine two."],
            }
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.feedback.summary, "  Summary with spaces.\n")
        self.assertEqual(
            result.feedback.strengths,
            ("  Leading spaces", "Trailing spaces  "),
        )
        self.assertEqual(result.feedback.improvements, ("Line one.\nLine two.",))

    def test_extra_fields_ignored(self) -> None:
        payload = _valid_review_payload(
            extra_root={"unused_root": "ignored"},
        )
        payload["feedback"]["unused_feedback"] = "ignored"
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.score, 8)
        self.assertEqual(result.feedback.summary, "Good answer with clear steps.")

    def test_score_zero_allowed(self) -> None:
        payload = _valid_review_payload(score=0, passed=False)
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.score, 0)

    def test_max_score_zero_allowed(self) -> None:
        payload = _valid_review_payload(score=0, max_score=0, passed=False)
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.max_score, 0)

    def test_passed_true(self) -> None:
        payload = _valid_review_payload(passed=True)
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertTrue(result.passed)

    def test_passed_false(self) -> None:
        payload = _valid_review_payload(passed=False)
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertFalse(result.passed)

    def test_identical_json_produces_equal_results(self) -> None:
        response = json.dumps(_valid_review_payload())

        first = self.parser.parse(response)
        second = self.parser.parse(response)

        self.assertEqual(first, second)


class ReviewResponseParserErrorTests(unittest.TestCase):
    """Tests for review parsing errors."""

    def setUp(self) -> None:
        self.parser = ReviewResponseParser()

    def test_invalid_json_raises_decode_error(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            self.parser.parse("{not valid json")

    def test_invalid_root_type(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps([]))

        self.assertEqual(
            str(context.exception),
            "Review response root must be a JSON object.",
        )

    def test_missing_score(self) -> None:
        payload = _valid_review_payload()
        del payload["score"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'score' is required.")

    def test_missing_max_score(self) -> None:
        payload = _valid_review_payload()
        del payload["max_score"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'max_score' is required.")

    def test_missing_passed(self) -> None:
        payload = _valid_review_payload()
        del payload["passed"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'passed' is required.")

    def test_missing_feedback(self) -> None:
        payload = _valid_review_payload()
        del payload["feedback"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'feedback' is required.")

    def test_score_invalid_types(self) -> None:
        invalid_values = ["8", 8.5, True, None]
        for value in invalid_values:
            with self.subTest(value=value):
                payload = _valid_review_payload(score=value)  # type: ignore[arg-type]

                with self.assertRaises(ValueError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'score' must be an integer.",
                )

    def test_max_score_invalid_types(self) -> None:
        invalid_values = ["10", 10.5, True, None]
        for value in invalid_values:
            with self.subTest(value=value):
                payload = _valid_review_payload(max_score=value)  # type: ignore[arg-type]

                with self.assertRaises(ValueError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'max_score' must be an integer.",
                )

    def test_passed_invalid_types(self) -> None:
        invalid_values = ["true", 1, None]
        for value in invalid_values:
            with self.subTest(value=value):
                payload = _valid_review_payload(passed=value)  # type: ignore[arg-type]

                with self.assertRaises(ValueError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'passed' must be a boolean.",
                )

    def test_feedback_invalid_types(self) -> None:
        invalid_values = ["feedback", [], None]
        for value in invalid_values:
            with self.subTest(value=value):
                payload = _valid_review_payload(feedback=value)  # type: ignore[arg-type]

                with self.assertRaises(ValueError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'feedback' must be a JSON object.",
                )

    def test_missing_feedback_summary(self) -> None:
        feedback = {
            "strengths": [],
            "improvements": [],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.summary' is required.",
        )

    def test_feedback_summary_invalid_type(self) -> None:
        feedback = {
            "summary": 123,
            "strengths": [],
            "improvements": [],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.summary' must be a string.",
        )

    def test_missing_strengths(self) -> None:
        feedback = {
            "summary": "Summary.",
            "improvements": [],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.strengths' is required.",
        )

    def test_strengths_not_list(self) -> None:
        feedback = {
            "summary": "Summary.",
            "strengths": "not a list",
            "improvements": [],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.strengths' must be a list.",
        )

    def test_strengths_non_string_item(self) -> None:
        feedback = {
            "summary": "Summary.",
            "strengths": ["valid", 42, "also valid"],
            "improvements": [],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.strengths' item at index 1 must be a string.",
        )

    def test_missing_improvements(self) -> None:
        feedback = {
            "summary": "Summary.",
            "strengths": [],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.improvements' is required.",
        )

    def test_improvements_not_list(self) -> None:
        feedback = {
            "summary": "Summary.",
            "strengths": [],
            "improvements": {"not": "a list"},
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.improvements' must be a list.",
        )

    def test_improvements_non_string_item(self) -> None:
        feedback = {
            "summary": "Summary.",
            "strengths": [],
            "improvements": [True, "valid"],
        }
        payload = _valid_review_payload(feedback=feedback)

        with self.assertRaises(ValueError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'feedback.improvements' item at index 0 must be a string.",
        )
