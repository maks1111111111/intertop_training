"""Application service for persisting AI-generated courses with quizzes.

Orchestrates course persistence, quiz generation, and quiz persistence
without coupling callers to individual pipeline components.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ai.interfaces import LessonGenerationResult
from app.ai.quiz_interfaces import QuizGenerationRequest, QuizGenerationResult
from app.ai.quiz_service import QuizGenerationService
from app.services.course_generation_persistence_service import (
    CourseGenerationPersistenceService,
)
from app.services.quiz_generation_persistence_service import (
    QuizGenerationPersistenceService,
)


@dataclass(frozen=True)
class CourseWithQuizGenerationResult:
    """Combined result of course and quiz generation and persistence."""

    course_directory: Path
    quiz_path: Path
    lesson_result: LessonGenerationResult
    quiz_result: QuizGenerationResult


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
    ) -> CourseWithQuizGenerationResult:
        """Persist a course, generate a quiz from its lessons, and save quiz.json.

        Args:
            lesson_result: Parsed AI output with lessons and optional metadata.
            destination: Parent directory for the course (typically ``courses/``).

        Returns:
            Paths and generation results for the persisted course and quiz.

        Raises:
            ValueError: If ``lesson_result.lessons`` is empty after course save.
        """
        course_directory = self._course_persistence_service.persist(
            lesson_result,
            destination,
        )

        if not lesson_result.lessons:
            raise ValueError("Cannot generate quiz for a course without lessons.")

        quiz_request = QuizGenerationRequest(
            lessons=tuple(lesson_result.lessons),
        )
        quiz_result = self._quiz_generation_service.generate_quiz(quiz_request)
        quiz_path = self._quiz_persistence_service.persist(
            quiz_result,
            course_directory,
        )

        return CourseWithQuizGenerationResult(
            course_directory=course_directory,
            quiz_path=quiz_path,
            lesson_result=lesson_result,
            quiz_result=quiz_result,
        )
