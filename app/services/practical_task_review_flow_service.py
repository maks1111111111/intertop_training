"""Application service for practical-task submission and AI review workflow.

Orchestrates pending attempt creation, AI review, and persistence of the
review outcome without coupling callers to individual repository or AI
components.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ai.review_interfaces import ReviewRequest, ReviewResult
from app.ai.review_service import PracticalTaskReviewService
from app.repositories import practical_task_attempt_repository


class PracticalTaskAttemptCreationError(Exception):
    """Raised when a practical-task attempt cannot be created."""


class PracticalTaskReviewCompletionError(Exception):
    """Raised when an AI review outcome cannot be persisted."""


@dataclass(frozen=True)
class PracticalTaskReviewFlowResult:
    """Combined result of a practical-task submission and AI review."""

    attempt_id: int
    review_result: ReviewResult


class PracticalTaskReviewFlowService:
    """Submit a learner answer, review it with AI, and persist the outcome."""

    def __init__(
        self,
        review_service: PracticalTaskReviewService,
    ) -> None:
        self._review_service = review_service

    def submit_and_review(
        self,
        db_path: Path,
        telegram_id: int,
        course_slug: str,
        lesson_slug: str,
        request: ReviewRequest,
    ) -> PracticalTaskReviewFlowResult:
        """Create a pending attempt, run AI review, and store the outcome.

        Args:
            db_path: SQLite database path.
            telegram_id: Telegram user identifier.
            course_slug: Course slug for the attempt.
            lesson_slug: Lesson slug for the attempt.
            request: Review input including task snapshot and learner answer.

        Returns:
            The created attempt id and parsed AI review result.

        Raises:
            PracticalTaskAttemptCreationError: If the user is unknown.
            PracticalTaskReviewCompletionError: If review persistence fails.
        """
        attempt_id = practical_task_attempt_repository.create_attempt(
            db_path,
            telegram_id=telegram_id,
            course_slug=course_slug,
            lesson_slug=lesson_slug,
            task_title=request.practical_task_title,
            task_description=request.practical_task_description,
            expected_result=request.expected_result,
            learner_answer=request.learner_answer,
        )
        if attempt_id is None:
            raise PracticalTaskAttemptCreationError(
                f"Cannot create practical-task attempt for telegram_id={telegram_id}."
            )

        review_result = self._review_service.review(request)

        if not practical_task_attempt_repository.complete_review(
            db_path,
            attempt_id,
            review_result,
        ):
            raise PracticalTaskReviewCompletionError(
                f"Cannot persist review for attempt_id={attempt_id}."
            )

        return PracticalTaskReviewFlowResult(
            attempt_id=attempt_id,
            review_result=review_result,
        )
