"""Tests for AI quiz provider interfaces (``app.ai.quiz_interfaces``)."""

from __future__ import annotations

import unittest
from typing import Optional, Tuple

from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationAI,
    QuizGenerationRequest,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.content.lesson_builder import LessonCandidate


def _sample_option(
    option_id: str = "a",
    text: str = "Option A",
    correct: bool = False,
) -> QuizOption:
    return QuizOption(id=option_id, text=text, correct=correct)


def _sample_question(
    question_id: str = "q1",
    lesson: str = "lesson_01",
    question: str = "What is safety?",
    options: Optional[Tuple[QuizOption, ...]] = None,
) -> QuizQuestion:
    if options is None:
        options = (
            _sample_option("a", "First option", correct=True),
            _sample_option("b", "Second option", correct=False),
        )
    return QuizQuestion(
        id=question_id,
        lesson=lesson,
        question=question,
        options=options,
    )


class QuizOptionTests(unittest.TestCase):
    """Tests for :class:`QuizOption`."""

    def test_equality(self) -> None:
        left = QuizOption(id="a", text="Answer", correct=True)
        right = QuizOption(id="a", text="Answer", correct=True)

        self.assertEqual(left, right)

    def test_immutable(self) -> None:
        option = QuizOption(id="a", text="Answer", correct=False)

        with self.assertRaises(AttributeError):
            option.correct = True  # type: ignore[misc]

    def test_correct_flag(self) -> None:
        correct_option = QuizOption(id="a", text="Correct", correct=True)
        incorrect_option = QuizOption(id="b", text="Incorrect", correct=False)

        self.assertTrue(correct_option.correct)
        self.assertFalse(incorrect_option.correct)


class QuizQuestionTests(unittest.TestCase):
    """Tests for :class:`QuizQuestion`."""

    def test_equality(self) -> None:
        options = (
            _sample_option("a", "One", correct=True),
            _sample_option("b", "Two", correct=False),
        )
        left = _sample_question(options=options)
        right = _sample_question(options=options)

        self.assertEqual(left, right)

    def test_immutable(self) -> None:
        question = _sample_question()

        with self.assertRaises(AttributeError):
            question.question = "Changed"  # type: ignore[misc]

    def test_tuple_usage_for_options(self) -> None:
        question = _sample_question()

        self.assertIsInstance(question.options, tuple)
        self.assertEqual(len(question.options), 2)
        self.assertTrue(all(isinstance(option, QuizOption) for option in question.options))


class GeneratedQuizTests(unittest.TestCase):
    """Tests for :class:`GeneratedQuiz`."""

    def test_empty_quiz(self) -> None:
        quiz = GeneratedQuiz(title="Final test", passing_score=80, questions=())

        self.assertEqual(quiz.title, "Final test")
        self.assertEqual(quiz.passing_score, 80)
        self.assertEqual(quiz.questions, ())
        self.assertIsInstance(quiz.questions, tuple)

    def test_single_question(self) -> None:
        quiz = GeneratedQuiz(
            title="Lesson quiz",
            passing_score=70,
            questions=(_sample_question(),),
        )

        self.assertEqual(len(quiz.questions), 1)
        self.assertEqual(quiz.questions[0].id, "q1")

    def test_multiple_questions(self) -> None:
        quiz = GeneratedQuiz(
            title="Course quiz",
            passing_score=80,
            questions=(
                _sample_question(question_id="q1"),
                _sample_question(question_id="q2", lesson="lesson_02"),
            ),
        )

        self.assertEqual(len(quiz.questions), 2)
        self.assertEqual(quiz.questions[0].id, "q1")
        self.assertEqual(quiz.questions[1].lesson, "lesson_02")


class QuizGenerationRequestTests(unittest.TestCase):
    """Tests for :class:`QuizGenerationRequest`."""

    def test_tuple_usage_for_lessons(self) -> None:
        lessons = (
            LessonCandidate(title="Lesson 1", content="Content 1."),
            LessonCandidate(title="Lesson 2", content="Content 2."),
        )
        request = QuizGenerationRequest(lessons=lessons)

        self.assertEqual(request.lessons, lessons)
        self.assertIsInstance(request.lessons, tuple)
        self.assertTrue(all(isinstance(lesson, LessonCandidate) for lesson in request.lessons))


class QuizGenerationResultTests(unittest.TestCase):
    """Tests for :class:`QuizGenerationResult`."""

    def test_create_result(self) -> None:
        quiz = GeneratedQuiz(
            title="Generated quiz",
            passing_score=80,
            questions=(_sample_question(),),
        )
        result = QuizGenerationResult(quiz=quiz)

        self.assertEqual(result.quiz, quiz)
        self.assertIsInstance(result.quiz, GeneratedQuiz)


class QuizGenerationAIProtocolTests(unittest.TestCase):
    """Tests for :class:`QuizGenerationAI` structural typing."""

    def test_protocol_accepts_conforming_implementation(self) -> None:
        class StubQuizAI:
            def generate_quiz(
                self,
                request: QuizGenerationRequest,
            ) -> QuizGenerationResult:
                quiz = GeneratedQuiz(
                    title="Stub quiz",
                    passing_score=80,
                    questions=(),
                )
                return QuizGenerationResult(quiz=quiz)

        ai: QuizGenerationAI = StubQuizAI()
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content."),
            )
        )

        result = ai.generate_quiz(request)

        self.assertIsInstance(result, QuizGenerationResult)
        self.assertEqual(result.quiz.title, "Stub quiz")
        self.assertEqual(result.quiz.questions, ())
