"""Write quiz drafts to the filesystem as runtime-compatible quiz.json.

Persists :class:`QuizDraft` as ``quiz.json`` using the Content Engine quiz
contract consumed by the runtime loader.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.content.contract import QUIZ_JSON_FILENAME
from app.content.quiz_writer import (
    QuizDraft,
    QuizOptionDraft,
    QuizQuestionDraft,
)


class QuizFileWriter:
    """Persist a :class:`QuizDraft` as ``quiz.json`` under a course directory."""

    def write(self, draft: QuizDraft, course_directory: Path) -> Path:
        """Write quiz metadata to ``course_directory / quiz.json``.

        Args:
            draft: In-memory quiz draft from :class:`QuizWriter`.
            course_directory: Existing course root directory.

        Returns:
            The resolved path to the written ``quiz.json`` file.

        Raises:
            FileNotFoundError: If ``course_directory`` does not exist.
            NotADirectoryError: If ``course_directory`` is not a directory.
        """
        if not course_directory.exists():
            raise FileNotFoundError(
                f"Course directory does not exist: {course_directory}"
            )

        if not course_directory.is_dir():
            raise NotADirectoryError(
                f"Course directory must be a directory: {course_directory}"
            )

        quiz_path = course_directory / QUIZ_JSON_FILENAME
        _write_json(quiz_path, _draft_to_manifest(draft))
        return quiz_path


def _draft_to_manifest(draft: QuizDraft) -> dict:
    return {
        "id": draft.id,
        "title": draft.title,
        "passing_score": draft.passing_score,
        "version": draft.version,
        "randomize_questions": draft.randomize_questions,
        "randomize_options": draft.randomize_options,
        "questions": [
            _question_to_manifest(question)
            for question in draft.questions
        ],
    }


def _question_to_manifest(question: QuizQuestionDraft) -> dict:
    return {
        "id": question.id,
        "type": question.question_type,
        "text": question.text,
        "options": [
            _option_to_manifest(option)
            for option in question.options
        ],
        "correct_option_ids": list(question.correct_option_ids),
        "explanation": question.explanation,
        "lesson": question.lesson,
        "difficulty": question.difficulty,
        "tags": list(question.tags),
        "ai_context": question.ai_context,
    }


def _option_to_manifest(option: QuizOptionDraft) -> dict:
    return {
        "id": option.id,
        "text": option.text,
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
