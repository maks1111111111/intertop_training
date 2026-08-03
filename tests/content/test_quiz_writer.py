"""Tests for quiz draft writing (``app.content.quiz_writer``)."""

from __future__ import annotations

import unittest

from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.content.quiz_writer import (
    QuizDraft,
    QuizOptionDraft,
    QuizQuestionDraft,
    QuizWriter,
)


def _sample_option(
    option_id: str,
    text: str,
    *,
    correct: bool = False,
) -> QuizOption:
    return QuizOption(id=option_id, text=text, correct=correct)


def _sample_question(
    question_id: str = "q1",
    *,
    lesson: str = "lesson_01",
    question_text: str = "What should an employee do?",
    options: tuple[QuizOption, ...] | None = None,
) -> QuizQuestion:
    if options is None:
        options = (
            _sample_option("a", "Correct answer", correct=True),
            _sample_option("b", "Incorrect answer 1"),
            _sample_option("c", "Incorrect answer 2"),
            _sample_option("d", "Incorrect answer 3"),
        )

    return QuizQuestion(
        id=question_id,
        lesson=lesson,
        question=question_text,
        options=options,
    )


def _sample_result(
    *,
    questions: tuple[QuizQuestion, ...] | None = None,
    title: str = "Final course quiz",
    passing_score: int = 80,
) -> QuizGenerationResult:
    if questions is None:
        questions = (_sample_question(),)

    return QuizGenerationResult(
        quiz=GeneratedQuiz(
            title=title,
            passing_score=passing_score,
            questions=questions,
        )
    )


class QuizWriterTests(unittest.TestCase):
    """Tests for :class:`QuizWriter`."""

    def setUp(self) -> None:
        self.writer = QuizWriter()

    def test_single_question_conversion(self) -> None:
        result = _sample_result()

        draft = self.writer.write(result, "brands")

        self.assertEqual(len(draft.questions), 1)
        self.assertEqual(draft.questions[0].id, "q1")
        self.assertEqual(draft.questions[0].text, "What should an employee do?")

    def test_multiple_questions_conversion(self) -> None:
        result = _sample_result(
            questions=(
                _sample_question("q1", question_text="First question"),
                _sample_question("q2", question_text="Second question"),
            )
        )

        draft = self.writer.write(result, "brands")

        self.assertEqual(len(draft.questions), 2)
        self.assertEqual(draft.questions[0].text, "First question")
        self.assertEqual(draft.questions[1].text, "Second question")

    def test_exact_quiz_draft_shape(self) -> None:
        result = _sample_result()

        draft = self.writer.write(result, "brands")

        self.assertEqual(
            draft,
            QuizDraft(
                id="brands_quiz",
                title="Final course quiz",
                passing_score=80,
                version=1,
                randomize_questions=True,
                randomize_options=True,
                questions=(
                    QuizQuestionDraft(
                        id="q1",
                        question_type="single_choice",
                        text="What should an employee do?",
                        options=(
                            QuizOptionDraft(id="a", text="Correct answer"),
                            QuizOptionDraft(id="b", text="Incorrect answer 1"),
                            QuizOptionDraft(id="c", text="Incorrect answer 2"),
                            QuizOptionDraft(id="d", text="Incorrect answer 3"),
                        ),
                        correct_option_ids=("a",),
                        explanation="",
                        lesson="lesson_01",
                        difficulty=1,
                        tags=(),
                        ai_context="",
                    ),
                ),
            ),
        )

    def test_quiz_id_uses_course_slug(self) -> None:
        draft = self.writer.write(_sample_result(), "service")

        self.assertEqual(draft.id, "service_quiz")

    def test_course_slug_is_stripped(self) -> None:
        draft = self.writer.write(_sample_result(), "  brands  ")

        self.assertEqual(draft.id, "brands_quiz")

    def test_title_and_passing_score_are_copied(self) -> None:
        result = _sample_result(title="Safety Quiz", passing_score=75)

        draft = self.writer.write(result, "brands")

        self.assertEqual(draft.title, "Safety Quiz")
        self.assertEqual(draft.passing_score, 75)

    def test_question_order_is_preserved(self) -> None:
        result = _sample_result(
            questions=(
                _sample_question("q1", question_text="First"),
                _sample_question("q2", question_text="Second"),
                _sample_question("q3", question_text="Third"),
            )
        )

        draft = self.writer.write(result, "brands")

        self.assertEqual(
            tuple(question.id for question in draft.questions),
            ("q1", "q2", "q3"),
        )

    def test_option_order_is_preserved(self) -> None:
        options = (
            _sample_option("z", "Last"),
            _sample_option("a", "First", correct=True),
            _sample_option("m", "Middle"),
            _sample_option("b", "Another"),
        )
        result = _sample_result(questions=(_sample_question(options=options),))

        draft = self.writer.write(result, "brands")

        self.assertEqual(
            tuple(option.id for option in draft.questions[0].options),
            ("z", "a", "m", "b"),
        )

    def test_correct_option_maps_to_correct_option_ids(self) -> None:
        draft = self.writer.write(_sample_result(), "brands")

        self.assertEqual(draft.questions[0].correct_option_ids, ("a",))

    def test_option_draft_has_no_correct_field(self) -> None:
        draft = self.writer.write(_sample_result(), "brands")

        option = draft.questions[0].options[0]
        self.assertEqual(
            set(vars(option).keys()),
            {"id", "text"},
        )

    def test_runtime_defaults(self) -> None:
        draft = self.writer.write(_sample_result(), "brands")
        question = draft.questions[0]

        self.assertEqual(draft.version, 1)
        self.assertTrue(draft.randomize_questions)
        self.assertTrue(draft.randomize_options)
        self.assertEqual(question.question_type, "single_choice")
        self.assertEqual(question.explanation, "")
        self.assertEqual(question.difficulty, 1)
        self.assertEqual(question.tags, ())
        self.assertEqual(question.ai_context, "")

    def test_questions_options_and_ids_use_tuples(self) -> None:
        draft = self.writer.write(_sample_result(), "brands")
        question = draft.questions[0]

        self.assertIsInstance(draft.questions, tuple)
        self.assertIsInstance(question.options, tuple)
        self.assertIsInstance(question.correct_option_ids, tuple)
        self.assertIsInstance(question.tags, tuple)

    def test_empty_course_slug_raises_value_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Course slug must be a non-empty string.",
        ):
            self.writer.write(_sample_result(), "")

    def test_whitespace_only_course_slug_raises_value_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Course slug must be a non-empty string.",
        ):
            self.writer.write(_sample_result(), "   ")

    def test_non_string_course_slug_raises_value_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Course slug must be a non-empty string.",
        ):
            self.writer.write(_sample_result(), 123)  # type: ignore[arg-type]

    def test_question_without_correct_option_raises_value_error(self) -> None:
        options = (
            _sample_option("a", "Option A"),
            _sample_option("b", "Option B"),
            _sample_option("c", "Option C"),
            _sample_option("d", "Option D"),
        )
        result = _sample_result(questions=(_sample_question(options=options),))

        with self.assertRaisesRegex(
            ValueError,
            "Question 'q1' must contain exactly one correct option.",
        ):
            self.writer.write(result, "brands")

    def test_question_with_multiple_correct_options_raises_value_error(self) -> None:
        options = (
            _sample_option("a", "Option A", correct=True),
            _sample_option("b", "Option B", correct=True),
            _sample_option("c", "Option C"),
            _sample_option("d", "Option D"),
        )
        result = _sample_result(questions=(_sample_question(options=options),))

        with self.assertRaisesRegex(
            ValueError,
            "Question 'q1' must contain exactly one correct option.",
        ):
            self.writer.write(result, "brands")

    def test_source_result_is_not_mutated(self) -> None:
        result = _sample_result()
        original_question = result.quiz.questions[0]
        original_options = original_question.options

        self.writer.write(result, "brands")

        self.assertEqual(original_question.id, "q1")
        self.assertEqual(original_options[0].correct, True)
        self.assertEqual(len(original_options), 4)


if __name__ == "__main__":
    unittest.main()
