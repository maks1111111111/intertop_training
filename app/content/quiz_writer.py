"""Convert AI quiz generation results into runtime-compatible in-memory drafts.

Maps :class:`QuizGenerationResult` to :class:`QuizDraft` without writing files
to disk. Output field names align with the Content Engine quiz contract used
by the runtime loader.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.quiz_interfaces import (
    QuizGenerationResult,
    QuizQuestion,
)

_DEFAULT_VERSION = 1
_DEFAULT_RANDOMIZE_QUESTIONS = True
_DEFAULT_RANDOMIZE_OPTIONS = True
_DEFAULT_QUESTION_TYPE = "single_choice"
_DEFAULT_EXPLANATION = ""
_DEFAULT_DIFFICULTY = 1
_DEFAULT_AI_CONTEXT = ""


@dataclass(frozen=True)
class QuizOptionDraft:
    """Runtime-compatible draft for a single quiz answer option."""

    id: str
    text: str


@dataclass(frozen=True)
class QuizQuestionDraft:
    """Runtime-compatible draft for a single quiz question."""

    id: str
    question_type: str
    text: str
    options: tuple[QuizOptionDraft, ...]
    correct_option_ids: tuple[str, ...]
    explanation: str
    lesson: str
    difficulty: int
    tags: tuple[str, ...]
    ai_context: str


@dataclass(frozen=True)
class QuizDraft:
    """Runtime-compatible in-memory quiz draft."""

    id: str
    title: str
    passing_score: int
    version: int
    randomize_questions: bool
    randomize_options: bool
    questions: tuple[QuizQuestionDraft, ...]


class QuizWriter:
    """Build a :class:`QuizDraft` from AI quiz generation results."""

    def write(
        self,
        result: QuizGenerationResult,
        course_slug: str,
    ) -> QuizDraft:
        """Convert a generation result into a runtime-compatible quiz draft.

        Args:
            result: Parsed AI quiz output.
            course_slug: Course directory slug used to build the quiz identifier.

        Returns:
            A :class:`QuizDraft` ready for downstream persistence layers.

        Raises:
            ValueError: If ``course_slug`` is invalid or a question has an
                incorrect number of correct options.
        """
        normalized_slug = _validate_course_slug(course_slug)
        quiz = result.quiz

        return QuizDraft(
            id=f"{normalized_slug}_quiz",
            title=quiz.title,
            passing_score=quiz.passing_score,
            version=_DEFAULT_VERSION,
            randomize_questions=_DEFAULT_RANDOMIZE_QUESTIONS,
            randomize_options=_DEFAULT_RANDOMIZE_OPTIONS,
            questions=tuple(
                _build_question_draft(question)
                for question in quiz.questions
            ),
        )


def _validate_course_slug(course_slug: str) -> str:
    if not isinstance(course_slug, str):
        raise ValueError("Course slug must be a non-empty string.")

    normalized_slug = course_slug.strip()
    if not normalized_slug:
        raise ValueError("Course slug must be a non-empty string.")

    return normalized_slug


def _build_question_draft(question: QuizQuestion) -> QuizQuestionDraft:
    correct_option_ids = _resolve_correct_option_ids(question)

    return QuizQuestionDraft(
        id=question.id,
        question_type=_DEFAULT_QUESTION_TYPE,
        text=question.question,
        options=tuple(
            QuizOptionDraft(id=option.id, text=option.text)
            for option in question.options
        ),
        correct_option_ids=correct_option_ids,
        explanation=_DEFAULT_EXPLANATION,
        lesson=question.lesson,
        difficulty=_DEFAULT_DIFFICULTY,
        tags=(),
        ai_context=_DEFAULT_AI_CONTEXT,
    )


def _resolve_correct_option_ids(question: QuizQuestion) -> tuple[str, ...]:
    correct_ids = tuple(
        option.id
        for option in question.options
        if option.correct
    )

    if len(correct_ids) != 1:
        raise ValueError(
            f"Question '{question.id}' must contain exactly one correct option."
        )

    return correct_ids
