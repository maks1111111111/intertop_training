"""Application service for persisting AI-generated courses with quizzes.

Orchestrates course persistence, quiz generation, and quiz persistence
without coupling callers to individual pipeline components.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.ai.interfaces import LessonGenerationResult
from app.ai.quiz_coverage import create_quiz_generation_request
from app.ai.quiz_interfaces import QuizGenerationResult
from app.ai.quiz_service import QuizGenerationService
from app.services.course_generation_persistence_service import (
    CourseGenerationPersistenceService,
)
from app.services.quiz_generation_persistence_service import (
    QuizGenerationPersistenceService,
)


def _is_safe_course_directory(course_directory: Path, destination: Path) -> bool:
    """Return True when ``course_directory`` is a child of ``destination``."""
    try:
        resolved_destination = destination.resolve()
        resolved_course_directory = course_directory.resolve()
    except OSError:
        return False

    if resolved_destination == resolved_course_directory:
        return False

    try:
        resolved_course_directory.relative_to(resolved_destination)
    except ValueError:
        return False

    return True


def _safe_remove_course_directory(course_directory: Path, destination: Path) -> None:
    """Remove a course directory created during this workflow if rollback is needed."""
    if not _is_safe_course_directory(course_directory, destination):
        return
    if not course_directory.is_dir():
        return
    try:
        shutil.rmtree(course_directory)
    except OSError:
        pass


@dataclass(frozen=True)
class CourseWithQuizGenerationResult:
    """Combined result of course and quiz generation and persistence."""

    course_directory: Path
    quiz_path: Optional[Path]
    lesson_result: LessonGenerationResult
    quiz_result: Optional[QuizGenerationResult]


class CourseWithQuizGenerationService:
    """Persist a generated course and its AI-generated quiz in one workflow."""

    def __init__(
        self,
        course_persistence_service: CourseGenerationPersistenceService,
        quiz_generation_service: QuizGenerationService,
        quiz_persistence_service: QuizGenerationPersistenceService,
    ) -> None:
        self._course_persistence_service = course_persistence_service
        self._quiz_generation_service = quiz_generation_service
        self._quiz_persistence_service = quiz_persistence_service

    def generate_and_persist(
        self,
        lesson_result: LessonGenerationResult,
        destination: Path,
        *,
        generate_quiz: bool = True,
        questions_per_lesson: int = 0,
        output_language: Optional[str] = None,
    ) -> CourseWithQuizGenerationResult:
        """Persist a course, optionally generate a quiz, and save quiz.json.

        Args:
            lesson_result: Parsed AI output with lessons and optional metadata.
            destination: Parent directory for the course (typically ``courses/``).
            generate_quiz: When ``False``, skip quiz generation and persistence.
            questions_per_lesson: Fixed per-lesson question count; ``0`` selects
                the adaptive content-length policy from ``quiz_coverage``.

        Returns:
            Paths and generation results for the persisted course and quiz.

        Raises:
            ValueError: If ``lesson_result.lessons`` is empty after course save.
        """
        course_directory = self._course_persistence_service.persist(
            lesson_result,
            destination,
        )

        try:
            if not lesson_result.lessons:
                raise ValueError(
                    "Cannot generate quiz for a course without lessons.",
                )

            if not generate_quiz:
                return CourseWithQuizGenerationResult(
                    course_directory=course_directory,
                    quiz_path=None,
                    lesson_result=lesson_result,
                    quiz_result=None,
                )

            quiz_request = create_quiz_generation_request(
                tuple(lesson_result.lessons),
                questions_per_lesson=questions_per_lesson,
                output_language=output_language,
            )
            quiz_result = self._quiz_generation_service.generate_quiz(quiz_request)
            quiz_path = self._quiz_persistence_service.persist(
                quiz_result,
                course_directory,
            )
        except Exception:
            _safe_remove_course_directory(course_directory, destination)
            raise

        return CourseWithQuizGenerationResult(
            course_directory=course_directory,
            quiz_path=quiz_path,
            lesson_result=lesson_result,
            quiz_result=quiz_result,
        )
