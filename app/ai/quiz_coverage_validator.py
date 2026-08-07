"""Validate that AI-generated quizzes meet requested lesson coverage."""

from __future__ import annotations

from collections import Counter

from app.ai.quiz_coverage import (
    lesson_slug_for_index,
    resolve_lesson_question_targets,
    total_question_target,
)
from app.ai.quiz_interfaces import QuizGenerationRequest, QuizGenerationResult


def validate_quiz_coverage(
    request: QuizGenerationRequest,
    result: QuizGenerationResult,
) -> None:
    """Ensure the generated quiz matches requested per-lesson question counts.

    Raises:
        ValueError: When total or per-lesson coverage does not match exactly,
            when unknown lesson slugs appear, or when duplicate question
            identifiers are present.
    """
    targets = resolve_lesson_question_targets(request)
    expected_total = total_question_target(request)
    actual_total = len(result.quiz.questions)
    allowed_slugs = {
        lesson_slug_for_index(lesson_index)
        for lesson_index, _ in enumerate(targets, start=1)
    }

    if actual_total != expected_total:
        raise ValueError(
            f"Generated quiz contains {actual_total} questions, "
            f"but exactly {expected_total} were required."
        )

    question_ids = [question.id for question in result.quiz.questions]
    duplicate_ids = sorted(
        question_id
        for question_id, count in Counter(question_ids).items()
        if count > 1
    )
    if duplicate_ids:
        joined = ", ".join(duplicate_ids)
        raise ValueError(f"Generated quiz contains duplicate question ids: {joined}.")

    counts_by_lesson: Counter[str] = Counter()
    for question in result.quiz.questions:
        if question.lesson not in allowed_slugs:
            raise ValueError(
                f"Generated quiz contains unknown lesson slug '{question.lesson}'."
            )
        counts_by_lesson[question.lesson] += 1

    for lesson_index, required_count in enumerate(targets, start=1):
        lesson_slug = lesson_slug_for_index(lesson_index)
        actual_count = counts_by_lesson.get(lesson_slug, 0)
        if actual_count != required_count:
            raise ValueError(
                f"Lesson '{lesson_slug}' requires exactly {required_count} questions, "
                f"but {actual_count} were generated."
            )
