"""Tests for quiz coverage validation (``app.ai.quiz_coverage_validator``)."""

from __future__ import annotations

import unittest

from app.ai.quiz_coverage import create_quiz_generation_request
from app.ai.quiz_coverage_validator import validate_quiz_coverage
from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.content.lesson_builder import LessonCandidate


def _option(option_id: str, *, correct: bool = False) -> QuizOption:
    return QuizOption(
        id=option_id,
        text=f"Text {option_id}",
        correct=correct,
    )


def _question(
    question_id: str,
    *,
    lesson: str = "lesson_01",
) -> QuizQuestion:
    return QuizQuestion(
        id=question_id,
        lesson=lesson,
        question=f"Question {question_id}?",
        options=(
            _option("a", correct=True),
            _option("b"),
            _option("c"),
            _option("d"),
        ),
    )


def _sample_request(*, lesson_count: int = 1) -> object:
    lessons = tuple(
        LessonCandidate(title=f"Lesson {index}", content="Brief lesson.")
        for index in range(1, lesson_count + 1)
    )
    return create_quiz_generation_request(lessons)


class QuizCoverageValidatorTests(unittest.TestCase):
    """Tests for :func:`validate_quiz_coverage`."""

    def test_valid_quiz_passes(self) -> None:
        request = _sample_request()
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(_question("q1"), _question("q2")),
            )
        )

        validate_quiz_coverage(request, result)

    def test_too_few_total_questions_raises(self) -> None:
        request = _sample_request()
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(_question("q1"),),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Generated quiz contains 1 questions, but exactly 2 were required.",
        ):
            validate_quiz_coverage(request, result)

    def test_exact_total_passes(self) -> None:
        request = _sample_request(lesson_count=2)
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(
                    _question("q1", lesson="lesson_01"),
                    _question("q2", lesson="lesson_01"),
                    _question("q3", lesson="lesson_02"),
                    _question("q4", lesson="lesson_02"),
                ),
            )
        )

        validate_quiz_coverage(request, result)

    def test_too_many_total_questions_raises(self) -> None:
        request = _sample_request()
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(
                    _question("q1"),
                    _question("q2"),
                    _question("q3"),
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Generated quiz contains 3 questions, but exactly 2 were required.",
        ):
            validate_quiz_coverage(request, result)

    def test_unknown_lesson_slug_raises(self) -> None:
        request = _sample_request()
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(
                    _question("q1", lesson="lesson_01"),
                    _question("q2", lesson="lesson_99"),
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "unknown lesson slug 'lesson_99'",
        ):
            validate_quiz_coverage(request, result)

    def test_missing_lesson_coverage_raises(self) -> None:
        request = _sample_request(lesson_count=2)
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(
                    _question("q1", lesson="lesson_01"),
                    _question("q2", lesson="lesson_01"),
                    _question("q3", lesson="lesson_01"),
                    _question("q4", lesson="lesson_01"),
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Lesson 'lesson_01' requires exactly 2 questions, but 4 were generated.",
        ):
            validate_quiz_coverage(request, result)

    def test_missing_lesson_with_matching_total_raises_for_empty_lesson(self) -> None:
        request = _sample_request(lesson_count=2)
        result_short = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(
                    _question("q1", lesson="lesson_01"),
                    _question("q2", lesson="lesson_01"),
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Generated quiz contains 2 questions, but exactly 4 were required.",
        ):
            validate_quiz_coverage(request, result_short)

    def test_duplicate_question_ids_raise(self) -> None:
        request = _sample_request()
        result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Quiz",
                passing_score=80,
                questions=(_question("q1"), _question("q1")),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "duplicate question ids: q1",
        ):
            validate_quiz_coverage(request, result)


if __name__ == "__main__":
    unittest.main()
