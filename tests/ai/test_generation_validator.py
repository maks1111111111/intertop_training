"""Tests for AI generation validator (``app.ai.generation_validator``)."""

from __future__ import annotations

import unittest

from app.ai.generation_validator import GenerationValidationReport, GenerationValidator
from app.ai.interfaces import LessonGenerationResult
from app.content.lesson_builder import LessonCandidate
from app.content.practical_task import PracticalTask


def _valid_lesson(**overrides: object) -> LessonCandidate:
    defaults = {
        "title": "Lesson title",
        "content": "Full lesson content.",
        "summary": "Short summary.",
        "learning_objectives": ("Objective one", "Objective two"),
    }
    defaults.update(overrides)
    return LessonCandidate(**defaults)


def _valid_practical_task(**overrides: object) -> PracticalTask:
    defaults = {
        "title": "Inspect the work area",
        "description": "Walk through the area and note hazards.",
        "expected_result": "All hazards are documented.",
        "estimated_minutes": 10,
    }
    defaults.update(overrides)
    return PracticalTask(**defaults)


def _empty_practical_task_counters() -> dict[str, int]:
    return {
        "empty_practical_task_titles": 0,
        "empty_practical_task_descriptions": 0,
        "empty_practical_task_expected_results": 0,
        "invalid_practical_task_estimates": 0,
    }


class GenerationValidatorTests(unittest.TestCase):
    """Tests for :class:`GenerationValidator`."""

    def setUp(self) -> None:
        self.validator = GenerationValidator()

    def test_fully_valid_result(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(),
                _valid_lesson(title="Second lesson"),
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(
            report,
            GenerationValidationReport(
                lessons=2,
                empty_contents=0,
                empty_summaries=0,
                empty_titles=0,
                empty_learning_objectives=0,
                valid=True,
                **_empty_practical_task_counters(),
            ),
        )

    def test_empty_content(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(content="")]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.lessons, 1)
        self.assertEqual(report.empty_contents, 1)
        self.assertEqual(report.empty_summaries, 0)
        self.assertEqual(report.empty_titles, 0)
        self.assertEqual(report.empty_learning_objectives, 0)
        self.assertEqual(report.empty_practical_task_titles, 0)
        self.assertEqual(report.empty_practical_task_descriptions, 0)
        self.assertEqual(report.empty_practical_task_expected_results, 0)
        self.assertEqual(report.invalid_practical_task_estimates, 0)
        self.assertFalse(report.valid)

    def test_whitespace_only_content(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(content="   ")]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_contents, 1)
        self.assertFalse(report.valid)

    def test_empty_summary(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(summary=None)]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_summaries, 1)
        self.assertFalse(report.valid)

    def test_whitespace_only_summary(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(summary="   ")]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_summaries, 1)
        self.assertFalse(report.valid)

    def test_empty_title(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(title="")]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_titles, 1)
        self.assertFalse(report.valid)

    def test_whitespace_only_title(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(title="   ")]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_titles, 1)
        self.assertFalse(report.valid)

    def test_empty_learning_objectives(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(learning_objectives=())]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_learning_objectives, 1)
        self.assertFalse(report.valid)

    def test_multiple_errors_at_once(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="",
                    content="",
                    summary=None,
                    learning_objectives=(),
                )
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_titles, 1)
        self.assertEqual(report.empty_summaries, 1)
        self.assertEqual(report.empty_contents, 1)
        self.assertEqual(report.empty_learning_objectives, 1)
        self.assertFalse(report.valid)

    def test_empty_lessons_list_is_valid(self) -> None:
        report = self.validator.validate(LessonGenerationResult(lessons=[]))

        self.assertEqual(report.lessons, 0)
        self.assertTrue(report.valid)

    def test_one_invalid_lesson_among_valid_ones(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(),
                _valid_lesson(content=""),
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.lessons, 2)
        self.assertEqual(report.empty_contents, 1)
        self.assertFalse(report.valid)

    def test_valid_result_with_all_quality_fields(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(
                    practical_task="Inspect the work area before opening.",
                    checklist=("Check equipment", "Review safety notes"),
                    common_mistakes=("Skipping the pre-shift briefing",),
                    key_takeaways=("Safety comes first",),
                    application_tips=("Apply the checklist daily",),
                )
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.lessons, 1)
        self.assertEqual(report.empty_contents, 0)
        self.assertEqual(report.empty_summaries, 0)
        self.assertEqual(report.empty_titles, 0)
        self.assertEqual(report.empty_learning_objectives, 0)
        self.assertTrue(report.valid)

    def test_legacy_lesson_with_empty_quality_fields(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(
                    practical_task="",
                    checklist=(),
                    common_mistakes=(),
                    key_takeaways=(),
                    application_tips=(),
                )
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.lessons, 1)
        self.assertTrue(report.valid)

    def test_valid_structured_practical_task(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(
                    structured_practical_task=_valid_practical_task(),
                )
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_practical_task_titles, 0)
        self.assertEqual(report.empty_practical_task_descriptions, 0)
        self.assertEqual(report.empty_practical_task_expected_results, 0)
        self.assertEqual(report.invalid_practical_task_estimates, 0)
        self.assertTrue(report.valid)

    def test_structured_practical_task_none_is_valid(self) -> None:
        result = LessonGenerationResult(
            lessons=[_valid_lesson(structured_practical_task=None)]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_practical_task_titles, 0)
        self.assertEqual(report.empty_practical_task_descriptions, 0)
        self.assertEqual(report.empty_practical_task_expected_results, 0)
        self.assertEqual(report.invalid_practical_task_estimates, 0)
        self.assertTrue(report.valid)

    def test_empty_practical_task_title(self) -> None:
        for title in ("", "   "):
            with self.subTest(title=title):
                result = LessonGenerationResult(
                    lessons=[
                        _valid_lesson(
                            structured_practical_task=_valid_practical_task(
                                title=title,
                            ),
                        )
                    ]
                )

                report = self.validator.validate(result)

                self.assertEqual(report.empty_practical_task_titles, 1)
                self.assertFalse(report.valid)

    def test_empty_practical_task_description(self) -> None:
        for description in ("", "   "):
            with self.subTest(description=description):
                result = LessonGenerationResult(
                    lessons=[
                        _valid_lesson(
                            structured_practical_task=_valid_practical_task(
                                description=description,
                            ),
                        )
                    ]
                )

                report = self.validator.validate(result)

                self.assertEqual(report.empty_practical_task_descriptions, 1)
                self.assertFalse(report.valid)

    def test_empty_practical_task_expected_result(self) -> None:
        for expected_result in ("", "   "):
            with self.subTest(expected_result=expected_result):
                result = LessonGenerationResult(
                    lessons=[
                        _valid_lesson(
                            structured_practical_task=_valid_practical_task(
                                expected_result=expected_result,
                            ),
                        )
                    ]
                )

                report = self.validator.validate(result)

                self.assertEqual(report.empty_practical_task_expected_results, 1)
                self.assertFalse(report.valid)

    def test_practical_task_estimated_minutes_none_is_valid(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(
                    structured_practical_task=_valid_practical_task(
                        estimated_minutes=None,
                    ),
                )
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.invalid_practical_task_estimates, 0)
        self.assertTrue(report.valid)

    def test_practical_task_positive_estimated_minutes(self) -> None:
        for estimated_minutes in (1, 15):
            with self.subTest(estimated_minutes=estimated_minutes):
                result = LessonGenerationResult(
                    lessons=[
                        _valid_lesson(
                            structured_practical_task=_valid_practical_task(
                                estimated_minutes=estimated_minutes,
                            ),
                        )
                    ]
                )

                report = self.validator.validate(result)

                self.assertEqual(report.invalid_practical_task_estimates, 0)
                self.assertTrue(report.valid)

    def test_invalid_practical_task_estimated_minutes(self) -> None:
        for estimated_minutes in (0, -5):
            with self.subTest(estimated_minutes=estimated_minutes):
                result = LessonGenerationResult(
                    lessons=[
                        _valid_lesson(
                            structured_practical_task=_valid_practical_task(
                                estimated_minutes=estimated_minutes,
                            ),
                        )
                    ]
                )

                report = self.validator.validate(result)

                self.assertEqual(report.invalid_practical_task_estimates, 1)
                self.assertFalse(report.valid)

    def test_multiple_structured_practical_task_errors_at_once(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(
                    structured_practical_task=PracticalTask(
                        title="",
                        description="   ",
                        expected_result="",
                        estimated_minutes=0,
                    ),
                )
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_practical_task_titles, 1)
        self.assertEqual(report.empty_practical_task_descriptions, 1)
        self.assertEqual(report.empty_practical_task_expected_results, 1)
        self.assertEqual(report.invalid_practical_task_estimates, 1)
        self.assertFalse(report.valid)

    def test_structured_practical_task_counters_sum_across_lessons(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                _valid_lesson(
                    structured_practical_task=_valid_practical_task(title=""),
                ),
                _valid_lesson(
                    structured_practical_task=_valid_practical_task(
                        description="",
                    ),
                ),
            ]
        )

        report = self.validator.validate(result)

        self.assertEqual(report.empty_practical_task_titles, 1)
        self.assertEqual(report.empty_practical_task_descriptions, 1)
        self.assertEqual(report.empty_practical_task_expected_results, 0)
        self.assertEqual(report.invalid_practical_task_estimates, 0)
        self.assertFalse(report.valid)


if __name__ == "__main__":
    unittest.main()
