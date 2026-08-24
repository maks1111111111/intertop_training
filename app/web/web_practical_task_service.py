"""Canonical-user practical task submission and AI review for Web."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Optional

from app.ai.review_interfaces import ReviewRequest, ReviewResult
from app.ai.review_language import resolve_review_language
from app.ai.review_service import PracticalTaskReviewService
from app.content.runtime import ContentRuntime
from app.repositories import practical_task_attempt_repository


class WebPracticalTaskValidationError(ValueError):
    """Raised when a Web practical-task submission is invalid."""


class WebPracticalTaskNotFoundError(Exception):
    """Raised when the requested course, lesson, or task is absent."""


class WebPracticalTaskAttemptCreationError(Exception):
    """Raised when a canonical attempt cannot be created."""


class WebPracticalTaskReviewUnavailableError(Exception):
    """Raised when AI practical-task review is unavailable."""


class WebPracticalTaskReviewCompletionError(Exception):
    """Raised when an AI review cannot be persisted."""


@dataclass(frozen=True)
class WebPracticalTaskSubmissionResult:
    attempt_id: int
    review_result: ReviewResult


class WebPracticalTaskService:
    """Submit and review practical tasks for canonical Web users."""

    def __init__(
        self,
        runtime: ContentRuntime,
        review_service: Optional[PracticalTaskReviewService],
        db_path: Path,
        repository: ModuleType = practical_task_attempt_repository,
    ) -> None:
        self._runtime = runtime
        self._review_service = review_service
        self._db_path = db_path
        self._repository = repository

    def submit_and_review(
        self,
        user_id: int,
        course_slug: str,
        lesson_id: str,
        learner_answer: str,
    ) -> WebPracticalTaskSubmissionResult:
        normalized_user_id = _validate_user_id(user_id)
        normalized_answer = _validate_learner_answer(learner_answer)

        course = self._runtime.get_course(course_slug)
        if course is None:
            raise WebPracticalTaskNotFoundError("Course not found.")

        lesson = next(
            (
                item
                for item in course.lessons
                if item.path.name == lesson_id
            ),
            None,
        )
        if lesson is None:
            raise WebPracticalTaskNotFoundError("Lesson not found.")

        task = lesson.structured_practical_task
        if task is None:
            raise WebPracticalTaskNotFoundError(
                "Structured practical task not found."
            )

        if self._review_service is None:
            raise WebPracticalTaskReviewUnavailableError(
                "AI practical-task review is unavailable."
            )

        request = ReviewRequest(
            lesson_title=lesson.title,
            practical_task_title=task.title,
            practical_task_description=task.description,
            expected_result=task.expected_result,
            learner_answer=normalized_answer,
            criteria=(),
            language=resolve_review_language(
                course.language,
                lesson.title,
                task.title,
                task.description,
                task.expected_result,
            ),
        )

        attempt_id = self._repository.create_attempt_for_user(
            self._db_path,
            user_id=normalized_user_id,
            course_slug=course_slug,
            lesson_slug=lesson.path.name,
            task_title=task.title,
            task_description=task.description,
            expected_result=task.expected_result,
            learner_answer=normalized_answer,
        )
        if attempt_id is None:
            raise WebPracticalTaskAttemptCreationError(
                f"Cannot create practical-task attempt for user_id={normalized_user_id}."
            )

        review_result = self._review_service.review(request)

        if not self._repository.complete_review(
            self._db_path,
            attempt_id,
            review_result,
        ):
            raise WebPracticalTaskReviewCompletionError(
                f"Cannot persist review for attempt_id={attempt_id}."
            )

        return WebPracticalTaskSubmissionResult(
            attempt_id=attempt_id,
            review_result=review_result,
        )

    def get_attempts_for_lesson(
        self,
        user_id: int,
        course_slug: str,
        lesson_id: str,
        limit: int = 10,
    ):
        normalized_user_id = _validate_user_id(user_id)
        return self._repository.get_attempts_for_lesson_for_user(
            self._db_path,
            user_id=normalized_user_id,
            course_slug=course_slug,
            lesson_slug=lesson_id,
            limit=limit,
        )


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise WebPracticalTaskValidationError(
            "user_id must be a positive integer"
        )
    return user_id


def _validate_learner_answer(learner_answer: str) -> str:
    if not isinstance(learner_answer, str):
        raise WebPracticalTaskValidationError(
            "learner_answer must be a string"
        )

    normalized = learner_answer.strip()
    if not normalized:
        raise WebPracticalTaskValidationError(
            "learner_answer must not be empty"
        )
    return normalized
