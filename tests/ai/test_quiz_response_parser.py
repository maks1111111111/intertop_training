"""Tests for AI quiz response parser (``app.ai.quiz_response_parser``)."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional

from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.ai.quiz_response_parser import QuizResponseParser


def _valid_option(
    option_id: str,
    text: str,
    correct: bool = False,
) -> Dict[str, Any]:
    return {"id": option_id, "text": text, "correct": correct}


def _valid_question(
    question_id: str = "q1",
    lesson: str = "lesson_01",
    question: str = "What should an employee do?",
    options: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if options is None:
        options = [
            _valid_option("a", "Correct answer", correct=True),
            _valid_option("b", "Incorrect answer 1"),
            _valid_option("c", "Incorrect answer 2"),
            _valid_option("d", "Incorrect answer 3"),
        ]
    return {
        "id": question_id,
        "lesson": lesson,
        "question": question,
        "options": options,
    }


def _valid_quiz_payload(
    title: str = "Final course quiz",
    passing_score: int = 80,
    questions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if questions is None:
        questions = [_valid_question()]
    return {
        "title": title,
        "passing_score": passing_score,
        "questions": questions,
    }


class QuizResponseParserSuccessTests(unittest.TestCase):
    """Tests for successful quiz parsing."""

    def setUp(self) -> None:
        self.parser = QuizResponseParser()

    def test_parse_single_question(self) -> None:
        response = json.dumps(_valid_quiz_payload())

        result = self.parser.parse_quiz(response)

        self.assertIsInstance(result, QuizGenerationResult)
        self.assertEqual(result.quiz.title, "Final course quiz")
        self.assertEqual(result.quiz.passing_score, 80)
        self.assertEqual(len(result.quiz.questions), 1)
        self.assertEqual(result.quiz.questions[0].id, "q1")
        self.assertEqual(result.quiz.questions[0].lesson, "lesson_01")
        self.assertEqual(
            result.quiz.questions[0].question,
            "What should an employee do?",
        )
        self.assertEqual(len(result.quiz.questions[0].options), 4)
        self.assertTrue(result.quiz.questions[0].options[0].correct)

    def test_parse_multiple_questions(self) -> None:
        payload = _valid_quiz_payload(
            questions=[
                _valid_question(question_id="q1", lesson="lesson_01"),
                _valid_question(
                    question_id="q2",
                    lesson="lesson_02",
                    question="Second question?",
                ),
            ]
        )
        response = json.dumps(payload)

        result = self.parser.parse_quiz(response)

        self.assertEqual(len(result.quiz.questions), 2)
        self.assertEqual(result.quiz.questions[0].id, "q1")
        self.assertEqual(result.quiz.questions[1].id, "q2")
        self.assertEqual(result.quiz.questions[1].lesson, "lesson_02")

    def test_strips_outer_whitespace_from_strings(self) -> None:
        payload = _valid_quiz_payload(
            title="  Final course quiz  ",
            questions=[
                {
                    "id": "  q1  ",
                    "lesson": "  lesson_01  ",
                    "question": "  What should an employee do?  ",
                    "options": [
                        _valid_option("  a  ", "  Correct answer  ", correct=True),
                        _valid_option("b", "Incorrect answer 1"),
                        _valid_option("c", "Incorrect answer 2"),
                        _valid_option("d", "Incorrect answer 3"),
                    ],
                }
            ],
        )
        response = json.dumps(payload)

        result = self.parser.parse_quiz(response)

        question = result.quiz.questions[0]
        self.assertEqual(result.quiz.title, "Final course quiz")
        self.assertEqual(question.id, "q1")
        self.assertEqual(question.lesson, "lesson_01")
        self.assertEqual(question.question, "What should an employee do?")
        self.assertEqual(question.options[0].id, "a")
        self.assertEqual(question.options[0].text, "Correct answer")

    def test_result_uses_tuple_for_questions_and_options(self) -> None:
        response = json.dumps(_valid_quiz_payload())

        result = self.parser.parse_quiz(response)

        self.assertIsInstance(result.quiz.questions, tuple)
        self.assertIsInstance(result.quiz.questions[0].options, tuple)

    def test_exact_result_matches_dataclass_models(self) -> None:
        response = json.dumps(_valid_quiz_payload())

        result = self.parser.parse_quiz(response)

        expected = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Final course quiz",
                passing_score=80,
                questions=(
                    QuizQuestion(
                        id="q1",
                        lesson="lesson_01",
                        question="What should an employee do?",
                        options=(
                            QuizOption(id="a", text="Correct answer", correct=True),
                            QuizOption(id="b", text="Incorrect answer 1", correct=False),
                            QuizOption(id="c", text="Incorrect answer 2", correct=False),
                            QuizOption(id="d", text="Incorrect answer 3", correct=False),
                        ),
                    ),
                ),
            )
        )
        self.assertEqual(result, expected)


class QuizResponseParserEmptyResponseTests(unittest.TestCase):
    """Tests for empty response handling."""

    def setUp(self) -> None:
        self.parser = QuizResponseParser()

    def test_empty_response_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz("")

        self.assertEqual(str(context.exception), "Response must not be empty.")


class QuizResponseParserJsonRootTests(unittest.TestCase):
    """Tests for JSON root validation."""

    def setUp(self) -> None:
        self.parser = QuizResponseParser()

    def test_invalid_json_raises_json_decode_error(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            self.parser.parse_quiz("{invalid")

    def test_non_object_root_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps([]))

        self.assertEqual(
            str(context.exception),
            "Response root must be a JSON object.",
        )


class QuizResponseParserTopLevelFieldTests(unittest.TestCase):
    """Tests for top-level field validation."""

    def setUp(self) -> None:
        self.parser = QuizResponseParser()

    def test_missing_title(self) -> None:
        payload = _valid_quiz_payload()
        del payload["title"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'title' is missing.")

    def test_missing_passing_score(self) -> None:
        payload = _valid_quiz_payload()
        del payload["passing_score"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'passing_score' is missing.",
        )

    def test_missing_questions(self) -> None:
        payload = _valid_quiz_payload()
        del payload["questions"]

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'questions' is missing.")

    def test_empty_title(self) -> None:
        payload = _valid_quiz_payload(title="   ")

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'title' must be a non-empty string.",
        )

    def test_invalid_passing_score_type(self) -> None:
        payload = _valid_quiz_payload()
        payload["passing_score"] = "80"

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'passing_score' must be an integer from 1 to 100.",
        )

    def test_passing_score_true_rejected(self) -> None:
        payload = _valid_quiz_payload()
        payload["passing_score"] = True

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'passing_score' must be an integer from 1 to 100.",
        )

    def test_passing_score_out_of_range(self) -> None:
        payload = _valid_quiz_payload(passing_score=0)

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'passing_score' must be an integer from 1 to 100.",
        )

    def test_empty_questions_list(self) -> None:
        payload = _valid_quiz_payload(questions=[])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'questions' must be a non-empty list.",
        )


class QuizResponseParserQuestionFieldTests(unittest.TestCase):
    """Tests for question-level validation."""

    def setUp(self) -> None:
        self.parser = QuizResponseParser()

    def test_question_not_object(self) -> None:
        payload = _valid_quiz_payload(questions=["invalid"])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 must be a JSON object.",
        )

    def test_missing_question_id(self) -> None:
        question = _valid_question()
        del question["id"]
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 is missing 'id'.",
        )

    def test_missing_question_lesson(self) -> None:
        question = _valid_question()
        del question["lesson"]
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 is missing 'lesson'.",
        )

    def test_missing_question_text(self) -> None:
        question = _valid_question()
        del question["question"]
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 is missing 'question'.",
        )

    def test_missing_question_options(self) -> None:
        question = _valid_question()
        del question["options"]
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 is missing 'options'.",
        )

    def test_empty_question_id(self) -> None:
        question = _valid_question()
        question["id"] = "   "
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 field 'id' must be a non-empty string.",
        )

    def test_empty_question_text_field(self) -> None:
        question = _valid_question()
        question["question"] = "   "
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 field 'question' must be a non-empty string.",
        )

    def test_duplicate_question_id(self) -> None:
        payload = _valid_quiz_payload(
            questions=[
                _valid_question(question_id="q1"),
                _valid_question(question_id="q1", lesson="lesson_02"),
            ]
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 1 has duplicate id 'q1'.",
        )

    def test_invalid_lesson_slug(self) -> None:
        question = _valid_question(lesson="lesson_1")
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 field 'lesson' must match format lesson_XX.",
        )

    def test_lesson_zero_slug_rejected(self) -> None:
        question = _valid_question(lesson="lesson_00")
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 field 'lesson' must match format lesson_XX.",
        )


class QuizResponseParserOptionsFieldTests(unittest.TestCase):
    """Tests for option-level validation."""

    def setUp(self) -> None:
        self.parser = QuizResponseParser()

    def test_options_not_list(self) -> None:
        question = _valid_question()
        question["options"] = "invalid"
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 field 'options' must be a list.",
        )

    def test_fewer_than_four_options(self) -> None:
        question = _valid_question(
            options=[
                _valid_option("a", "One", correct=True),
                _valid_option("b", "Two"),
                _valid_option("c", "Three"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 field 'options' must contain at least 4 items.",
        )

    def test_option_not_object(self) -> None:
        question = _valid_question()
        question["options"] = [
            _valid_option("a", "One", correct=True),
            _valid_option("b", "Two"),
            _valid_option("c", "Three"),
            "invalid",
        ]
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 option at index 3 must be a JSON object.",
        )

    def test_missing_option_id(self) -> None:
        option = _valid_option("a", "One", correct=True)
        del option["id"]
        question = _valid_question(
            options=[
                option,
                _valid_option("b", "Two"),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 option at index 0 is missing 'id'.",
        )

    def test_missing_option_text(self) -> None:
        option = _valid_option("a", "One", correct=True)
        del option["text"]
        question = _valid_question(
            options=[
                option,
                _valid_option("b", "Two"),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 option at index 0 is missing 'text'.",
        )

    def test_empty_option_text(self) -> None:
        question = _valid_question(
            options=[
                _valid_option("a", "   ", correct=True),
                _valid_option("b", "Two"),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 option at index 0 field 'text' must be a non-empty string.",
        )

    def test_correct_not_bool(self) -> None:
        option = _valid_option("a", "One", correct=True)
        option["correct"] = "true"
        question = _valid_question(
            options=[
                option,
                _valid_option("b", "Two"),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 option at index 0 field 'correct' must be a boolean.",
        )

    def test_duplicate_option_id(self) -> None:
        question = _valid_question(
            options=[
                _valid_option("a", "One", correct=True),
                _valid_option("a", "Two"),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 option at index 1 has duplicate id 'a'.",
        )

    def test_no_correct_option(self) -> None:
        question = _valid_question(
            options=[
                _valid_option("a", "One"),
                _valid_option("b", "Two"),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 must contain exactly one correct option.",
        )

    def test_multiple_correct_options(self) -> None:
        question = _valid_question(
            options=[
                _valid_option("a", "One", correct=True),
                _valid_option("b", "Two", correct=True),
                _valid_option("c", "Three"),
                _valid_option("d", "Four"),
            ]
        )
        payload = _valid_quiz_payload(questions=[question])

        with self.assertRaises(ValueError) as context:
            self.parser.parse_quiz(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Question at index 0 must contain exactly one correct option.",
        )
