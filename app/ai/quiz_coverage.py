"""Deterministic quiz question-count policy for AI generation.

Computes how many questions each lesson should receive based on content
volume. Used by the quiz prompt builder and post-generation validation.
"""

from __future__ import annotations

from typing import Tuple

from app.ai.quiz_interfaces import QuizGenerationRequest
from app.content.lesson_builder import LessonCandidate

MIN_QUESTIONS_PER_LESSON = 2
MEDIUM_QUESTIONS_PER_LESSON = 3
MAX_QUESTIONS_PER_LESSON = 4

SHORT_LESSON_CHAR_THRESHOLD = 800
LONG_LESSON_CHAR_THRESHOLD = 2000

# Soft cap on total quiz size. Per-lesson targets are reduced only while every
# lesson stays at or above MIN_QUESTIONS_PER_LESSON. When minimum coverage
# alone exceeds this cap (for example 15 short lessons × 2), the total may
# legitimately exceed MAX_TOTAL_QUESTIONS.
MAX_TOTAL_QUESTIONS = 24


def lesson_slug_for_index(index: int) -> str:
    """Return the canonical lesson slug for a 1-based lesson index."""
    return f"lesson_{index:02d}"


def compute_question_target_for_lesson(lesson: LessonCandidate) -> int:
    """Return the target number of quiz questions for one lesson.

    Policy (by stripped content length):
    - under 800 characters: 2 questions
    - under 2000 characters: 3 questions
    - otherwise: 4 questions
    """
    content_length = len(lesson.content.strip())

    if content_length < SHORT_LESSON_CHAR_THRESHOLD:
        return MIN_QUESTIONS_PER_LESSON
    if content_length < LONG_LESSON_CHAR_THRESHOLD:
        return MEDIUM_QUESTIONS_PER_LESSON
    return MAX_QUESTIONS_PER_LESSON


def _cap_total_targets(targets: list[int]) -> Tuple[int, ...]:
    """Apply the soft total cap without dropping any lesson below its minimum."""
    capped = list(targets)
    total = sum(capped)

    while total > MAX_TOTAL_QUESTIONS:
        max_value = max(capped)
        max_index = capped.index(max_value)
        if capped[max_index] <= MIN_QUESTIONS_PER_LESSON:
            break
        capped[max_index] -= 1
        total -= 1

    return tuple(capped)


def compute_lesson_question_targets(
    lessons: Tuple[LessonCandidate, ...],
    *,
    questions_per_lesson: int = 0,
) -> Tuple[int, ...]:
    """Compute per-lesson question targets for the given lessons.

    When ``questions_per_lesson`` is greater than zero, that fixed count is
    applied to every lesson (still capped per lesson and in total).
    Otherwise the auto-policy based on content length is used.
    """
    if not lessons:
        return ()

    if questions_per_lesson > 0:
        per_lesson = min(questions_per_lesson, MAX_QUESTIONS_PER_LESSON)
        targets = [per_lesson] * len(lessons)
    else:
        targets = [
            compute_question_target_for_lesson(lesson)
            for lesson in lessons
        ]

    return _cap_total_targets(targets)


def resolve_lesson_question_targets(
    request: QuizGenerationRequest,
) -> Tuple[int, ...]:
    """Return effective per-lesson targets for a generation request."""
    if request.lesson_question_targets:
        return request.lesson_question_targets
    return compute_lesson_question_targets(
        request.lessons,
        questions_per_lesson=request.questions_per_lesson,
    )


def total_question_target(request: QuizGenerationRequest) -> int:
    """Return the total number of questions required for a request."""
    return sum(resolve_lesson_question_targets(request))


def create_quiz_generation_request(
    lessons: Tuple[LessonCandidate, ...],
    *,
    questions_per_lesson: int = 0,
) -> QuizGenerationRequest:
    """Build a :class:`QuizGenerationRequest` with computed lesson targets."""
    targets = compute_lesson_question_targets(
        lessons,
        questions_per_lesson=questions_per_lesson,
    )
    return QuizGenerationRequest(
        lessons=lessons,
        questions_per_lesson=questions_per_lesson,
        lesson_question_targets=targets,
    )
