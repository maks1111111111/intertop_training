"""Parse AI model responses into structured quiz generation results."""

from __future__ import annotations

import json
import re
from typing import Any, Tuple

from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)

_LESSON_SLUG_PATTERN = re.compile(r"^lesson_(0[1-9]|[1-9]\d)$")
_MIN_OPTIONS_PER_QUESTION = 4


class QuizResponseParser:
    """Convert raw AI text responses into :class:`QuizGenerationResult`."""

    def parse_quiz(self, response: str) -> QuizGenerationResult:
        """Parse model output into quiz generation results.

        An empty response is invalid. Non-empty responses must be valid JSON
        matching the structured quiz generation contract.
        """
        if response == "":
            raise ValueError("Response must not be empty.")

        data = json.loads(response)
        if not isinstance(data, dict):
            raise ValueError("Response root must be a JSON object.")

        title = _parse_title(data)
        passing_score = _parse_passing_score(data)
        questions = _parse_questions(data)

        quiz = GeneratedQuiz(
            title=title,
            passing_score=passing_score,
            questions=questions,
        )
        return QuizGenerationResult(quiz=quiz)


def _parse_title(data: dict[str, Any]) -> str:
    if "title" not in data:
        raise ValueError("Field 'title' is missing.")

    title = data["title"]
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Field 'title' must be a non-empty string.")

    return title.strip()


def _parse_passing_score(data: dict[str, Any]) -> int:
    if "passing_score" not in data:
        raise ValueError("Field 'passing_score' is missing.")

    passing_score = data["passing_score"]
    if isinstance(passing_score, bool) or not isinstance(passing_score, int):
        raise ValueError("Field 'passing_score' must be an integer from 1 to 100.")

    if passing_score < 1 or passing_score > 100:
        raise ValueError("Field 'passing_score' must be an integer from 1 to 100.")

    return passing_score


def _parse_questions(data: dict[str, Any]) -> Tuple[QuizQuestion, ...]:
    if "questions" not in data:
        raise ValueError("Field 'questions' is missing.")

    raw_questions = data["questions"]
    if not isinstance(raw_questions, list) or len(raw_questions) == 0:
        raise ValueError("Field 'questions' must be a non-empty list.")

    seen_question_ids: set[str] = set()
    questions: list[QuizQuestion] = []
    for index, item in enumerate(raw_questions):
        question = _parse_question_item(item, index, seen_question_ids)
        questions.append(question)

    return tuple(questions)


def _parse_question_item(
    item: Any,
    index: int,
    seen_question_ids: set[str],
) -> QuizQuestion:
    if not isinstance(item, dict):
        raise ValueError(f"Question at index {index} must be a JSON object.")

    question_id = _parse_question_id(item, index, seen_question_ids)
    lesson = _parse_question_lesson(item, index)
    question_text = _parse_question_text(item, index)
    options = _parse_question_options(item, index)

    return QuizQuestion(
        id=question_id,
        lesson=lesson,
        question=question_text,
        options=options,
    )


def _parse_question_id(
    item: dict[str, Any],
    index: int,
    seen_question_ids: set[str],
) -> str:
    if "id" not in item:
        raise ValueError(f"Question at index {index} is missing 'id'.")

    question_id = item["id"]
    if not isinstance(question_id, str) or not question_id.strip():
        raise ValueError(
            f"Question at index {index} field 'id' must be a non-empty string."
        )

    normalized_id = question_id.strip()
    if normalized_id in seen_question_ids:
        raise ValueError(
            f"Question at index {index} has duplicate id '{normalized_id}'."
        )

    seen_question_ids.add(normalized_id)
    return normalized_id


def _parse_question_lesson(item: dict[str, Any], index: int) -> str:
    if "lesson" not in item:
        raise ValueError(f"Question at index {index} is missing 'lesson'.")

    lesson = item["lesson"]
    if not isinstance(lesson, str) or not lesson.strip():
        raise ValueError(
            f"Question at index {index} field 'lesson' must be a non-empty string."
        )

    normalized_lesson = lesson.strip()
    if not _LESSON_SLUG_PATTERN.match(normalized_lesson):
        raise ValueError(
            f"Question at index {index} field 'lesson' must match format lesson_XX."
        )

    return normalized_lesson


def _parse_question_text(item: dict[str, Any], index: int) -> str:
    if "question" not in item:
        raise ValueError(f"Question at index {index} is missing 'question'.")

    question_text = item["question"]
    if not isinstance(question_text, str) or not question_text.strip():
        raise ValueError(
            f"Question at index {index} field 'question' must be a non-empty string."
        )

    return question_text.strip()


def _parse_question_options(
    item: dict[str, Any],
    index: int,
) -> Tuple[QuizOption, ...]:
    if "options" not in item:
        raise ValueError(f"Question at index {index} is missing 'options'.")

    raw_options = item["options"]
    if not isinstance(raw_options, list):
        raise ValueError(
            f"Question at index {index} field 'options' must be a list."
        )

    if len(raw_options) < _MIN_OPTIONS_PER_QUESTION:
        raise ValueError(
            f"Question at index {index} field 'options' must contain at least "
            f"{_MIN_OPTIONS_PER_QUESTION} items."
        )

    seen_option_ids: set[str] = set()
    options: list[QuizOption] = []
    correct_count = 0

    for option_index, raw_option in enumerate(raw_options):
        option = _parse_option_item(raw_option, index, option_index, seen_option_ids)
        options.append(option)
        if option.correct:
            correct_count += 1

    if correct_count == 0:
        raise ValueError(
            f"Question at index {index} must contain exactly one correct option."
        )

    if correct_count > 1:
        raise ValueError(
            f"Question at index {index} must contain exactly one correct option."
        )

    return tuple(options)


def _parse_option_item(
    raw_option: Any,
    question_index: int,
    option_index: int,
    seen_option_ids: set[str],
) -> QuizOption:
    if not isinstance(raw_option, dict):
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "must be a JSON object."
        )

    if "id" not in raw_option:
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "is missing 'id'."
        )

    option_id = raw_option["id"]
    if not isinstance(option_id, str) or not option_id.strip():
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "field 'id' must be a non-empty string."
        )

    normalized_id = option_id.strip()
    if normalized_id in seen_option_ids:
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            f"has duplicate id '{normalized_id}'."
        )
    seen_option_ids.add(normalized_id)

    if "text" not in raw_option:
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "is missing 'text'."
        )

    option_text = raw_option["text"]
    if not isinstance(option_text, str) or not option_text.strip():
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "field 'text' must be a non-empty string."
        )

    if "correct" not in raw_option:
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "is missing 'correct'."
        )

    correct = raw_option["correct"]
    if not isinstance(correct, bool):
        raise ValueError(
            f"Question at index {question_index} option at index {option_index} "
            "field 'correct' must be a boolean."
        )

    return QuizOption(
        id=normalized_id,
        text=option_text.strip(),
        correct=correct,
    )
