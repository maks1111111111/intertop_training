"""Student dashboard data for the Web UI.

This module builds course-level dashboard rows from published runtime content.
Database aggregation for progress and quiz statistics will be added in a
later step; for now ``DashboardService`` returns placeholder metrics while
keeping repository dependencies wired for future use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.content.runtime import ContentRuntime
from app.repositories import quiz_repository as QuizRepository
from app.repositories.progress_repository import ProgressRepository

DEFAULT_STATUS = "not_started"


@dataclass(frozen=True)
class CourseDashboardItem:
    """One course row on the student dashboard."""

    slug: str
    title: str
    description: str
    status: str
    progress_percent: int
    best_quiz_score: Optional[float]
    last_quiz_score: Optional[float]
    last_lesson_title: str
    continue_url: str


class DashboardService:
    """Assemble student dashboard rows from runtime content and repositories."""

    def __init__(
        self,
        runtime: ContentRuntime,
        progress_repository: ProgressRepository,
        quiz_repository: QuizRepository,
    ) -> None:
        self._runtime = runtime
        self._progress_repository = progress_repository
        self._quiz_repository = quiz_repository

    def get_courses_for_user(self, telegram_id: int) -> tuple[CourseDashboardItem, ...]:
        """Return dashboard rows for *telegram_id*.

        ``telegram_id`` is accepted for future repository lookups. Current
        implementation returns placeholder progress and quiz metrics derived
        only from published runtime courses.
        """
        del telegram_id

        items: list[CourseDashboardItem] = []
        for course in self._runtime.get_courses():
            last_lesson_title = ""
            continue_url = f"/courses/{course.slug}"
            if course.lessons:
                first_lesson = course.lessons[0]
                last_lesson_title = first_lesson.title
                continue_url = (
                    f"/courses/{course.slug}/lessons/{first_lesson.path.name}"
                )

            items.append(
                CourseDashboardItem(
                    slug=course.slug,
                    title=course.title,
                    description=course.description,
                    status=DEFAULT_STATUS,
                    progress_percent=0,
                    best_quiz_score=None,
                    last_quiz_score=None,
                    last_lesson_title=last_lesson_title,
                    continue_url=continue_url,
                )
            )

        return tuple(items)
