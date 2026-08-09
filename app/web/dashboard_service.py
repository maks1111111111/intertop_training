"""Student dashboard data for the Web UI.

This module builds course-level dashboard rows from published runtime content
and SQLite-backed progress and quiz statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Optional

from app.content.runtime import ContentRuntime
from app.repositories.progress_repository import ProgressRepository
from app.content.runtime_loader import Course

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
        quiz_repository: ModuleType,
        db_path: Path,
    ) -> None:
        self._runtime = runtime
        self._progress_repository = progress_repository
        self._quiz_repository = quiz_repository
        self._db_path = db_path

    def get_courses_for_user(self, telegram_id: int) -> tuple[CourseDashboardItem, ...]:
        """Return dashboard rows for *telegram_id*."""
        items: list[CourseDashboardItem] = []
        for course in self._runtime.get_courses():
            status, progress_percent = self._progress_repository.get_course_progress(
                self._db_path,
                telegram_id,
                course.slug,
            )
            quiz_stats = self._quiz_repository.get_course_quiz_stats(
                self._db_path,
                telegram_id,
                course.slug,
            )
            resume_lesson_index = self._progress_repository.get_resume_lesson_index(
                self._db_path,
                telegram_id,
                course.slug,
            )

            items.append(
                CourseDashboardItem(
                    slug=course.slug,
                    title=course.title,
                    description=course.description,
                    status=status,
                    progress_percent=progress_percent,
                    best_quiz_score=quiz_stats["best_score_percent"],
                    last_quiz_score=quiz_stats["latest_score_percent"],
                    last_lesson_title=_last_lesson_title(course, resume_lesson_index),
                    continue_url=_continue_url(
                        course,
                        status,
                        resume_lesson_index,
                    ),
                )
            )

        return tuple(items)


def _last_lesson_title(course: Course, resume_lesson_index: int) -> str:
    """Return the title of the last completed lesson, if any."""
    if resume_lesson_index <= 0 or not course.lessons:
        return ""

    lesson_index = resume_lesson_index - 1
    if lesson_index >= len(course.lessons):
        lesson_index = len(course.lessons) - 1

    return course.lessons[lesson_index].title


def _continue_url(
    course: Course,
    status: str,
    resume_lesson_index: int,
) -> str:
    """Return the dashboard continue link for one course."""
    if status == DEFAULT_STATUS:
        return f"/courses/{course.slug}"

    if not course.lessons:
        return f"/courses/{course.slug}"

    lesson_index = resume_lesson_index
    if lesson_index >= len(course.lessons):
        lesson_index = len(course.lessons) - 1

    lesson = course.lessons[lesson_index]
    return f"/courses/{course.slug}/lessons/{lesson.path.name}"
