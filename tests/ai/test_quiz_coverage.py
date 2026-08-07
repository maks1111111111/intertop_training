"""Tests for quiz question-count policy (``app.ai.quiz_coverage``)."""

from __future__ import annotations

import unittest

from app.ai.quiz_coverage import (
    MAX_QUESTIONS_PER_LESSON,
    MAX_TOTAL_QUESTIONS,
    MIN_QUESTIONS_PER_LESSON,
    compute_lesson_question_targets,
    compute_question_target_for_lesson,
    create_quiz_generation_request,
    lesson_slug_for_index,
    total_question_target,
)
from app.content.lesson_builder import LessonCandidate


def _lesson(content: str, *, title: str = "Lesson") -> LessonCandidate:
    return LessonCandidate(title=title, content=content)


class QuizCoveragePolicyTests(unittest.TestCase):
    """Tests for deterministic quiz coverage policy."""

    def test_short_lesson_gets_minimum_two_questions(self) -> None:
        lesson = _lesson("Short lesson text.")

        self.assertEqual(compute_question_target_for_lesson(lesson), 2)

    def test_medium_lesson_gets_three_questions(self) -> None:
        content = "x" * 900

        self.assertEqual(
            compute_question_target_for_lesson(_lesson(content)),
            3,
        )

    def test_long_lesson_gets_four_questions(self) -> None:
        content = "x" * 2100

        self.assertEqual(
            compute_question_target_for_lesson(_lesson(content)),
            4,
        )

    def test_long_lesson_target_exceeds_short_lesson_target(self) -> None:
        short = compute_question_target_for_lesson(_lesson("Brief."))
        long = compute_question_target_for_lesson(_lesson("x" * 2500))

        self.assertLess(short, long)

    def test_multiple_lessons_sum_targets(self) -> None:
        lessons = (
            _lesson("Brief."),
            _lesson("x" * 900),
            _lesson("x" * 2500),
        )
        targets = compute_lesson_question_targets(lessons)

        self.assertEqual(targets, (2, 3, 4))
        self.assertEqual(sum(targets), 9)

    def test_policy_is_deterministic(self) -> None:
        lessons = (_lesson("x" * 950, title="A"),)

        first = compute_lesson_question_targets(lessons)
        second = compute_lesson_question_targets(lessons)

        self.assertEqual(first, second)

    def test_explicit_questions_per_lesson_override(self) -> None:
        lessons = (_lesson("Brief."), _lesson("Also brief."))

        targets = compute_lesson_question_targets(
            lessons,
            questions_per_lesson=3,
        )

        self.assertEqual(targets, (3, 3))

    def test_total_target_capped_at_maximum(self) -> None:
        lessons = tuple(
            _lesson("x" * 2500, title=f"Lesson {index}")
            for index in range(10)
        )

        targets = compute_lesson_question_targets(lessons)

        self.assertEqual(sum(targets), MAX_TOTAL_QUESTIONS)
        self.assertTrue(all(count >= MIN_QUESTIONS_PER_LESSON for count in targets))
        self.assertLess(max(targets), MAX_QUESTIONS_PER_LESSON)

    def test_many_short_lessons_keep_minimum_above_soft_cap(self) -> None:
        lessons = tuple(
            _lesson("Brief.", title=f"Lesson {index}")
            for index in range(15)
        )

        targets = compute_lesson_question_targets(lessons)

        self.assertEqual(targets, (2,) * 15)
        self.assertEqual(sum(targets), 30)
        self.assertGreater(sum(targets), MAX_TOTAL_QUESTIONS)

    def test_create_request_includes_lesson_targets(self) -> None:
        lessons = (_lesson("Brief."), _lesson("x" * 900))

        request = create_quiz_generation_request(lessons)

        self.assertEqual(request.lesson_question_targets, (2, 3))
        self.assertEqual(total_question_target(request), 5)

    def test_lesson_slug_for_index(self) -> None:
        self.assertEqual(lesson_slug_for_index(1), "lesson_01")
        self.assertEqual(lesson_slug_for_index(6), "lesson_06")

    def test_max_questions_per_lesson_constant(self) -> None:
        self.assertEqual(MAX_QUESTIONS_PER_LESSON, 4)


if __name__ == "__main__":
    unittest.main()
