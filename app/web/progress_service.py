"""SQLite-backed lesson progress for the read-only Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Optional

from app.database.db import get_connection
from app.repositories.progress_repository import ProgressRepository


@dataclass(frozen=True)
class LessonProgressRow:
    """One lesson row for the course detail page."""

    id: str
    title: str
    order: int
    status: str
    status_label: str


@dataclass(frozen=True)
class CourseProgressView:
    """Aggregated course progress for Web templates."""

    percent: int
    completed_count: int
    total_count: int
    is_completed: bool
    completion_message: Optional[str]
    lesson_rows: tuple[LessonProgressRow, ...]


def _validate_user_id(user_id: int) -> int:
    """Validate the canonical user id used by Web progress."""
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    return user_id


class WebProgressService:
    """Persist and read Web lesson completion through canonical progress tables."""

    def __init__(
        self,
        db_path: Path,
        progress_repository: ProgressRepository,
        user_id: int,
    ) -> None:
        self._db_path = db_path
        self._progress_repository = progress_repository
        self._user_id = _validate_user_id(user_id)

    def mark_lesson_completed(self, course_slug: str, lesson_id: str) -> None:
        """Record one completed lesson without creating duplicates."""
        if not self._user_exists():
            return

        self._progress_repository.start_course_for_user(
            self._db_path,
            self._user_id,
            course_slug,
        )
        self._progress_repository.complete_lesson_for_user(
            self._db_path,
            self._user_id,
            course_slug,
            lesson_id,
        )

    def is_lesson_completed(self, course_slug: str, lesson_id: str) -> bool:
        """Return whether the lesson is marked completed for the current user."""
        if not self._user_exists():
            return False

        with get_connection(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM lesson_progress
                JOIN lessons
                    ON lessons.id = lesson_progress.lesson_id
                JOIN courses
                    ON courses.id = lessons.course_id
                WHERE lesson_progress.user_id = ?
                  AND courses.slug = ?
                  AND lessons.slug = ?
                  AND lesson_progress.status = 'completed'
                LIMIT 1
                """,
                (self._user_id, course_slug, lesson_id),
            ).fetchone()
        return row is not None

    def completed_lessons(self, course_slug: str) -> set[str]:
        """Return lesson ids completed by the current user in one course."""
        if not self._user_exists():
            return set()

        with get_connection(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT lessons.slug
                FROM lesson_progress
                JOIN lessons
                    ON lessons.id = lesson_progress.lesson_id
                JOIN courses
                    ON courses.id = lessons.course_id
                WHERE lesson_progress.user_id = ?
                  AND courses.slug = ?
                  AND lesson_progress.status = 'completed'
                ORDER BY lessons.slug
                """,
                (self._user_id, course_slug),
            ).fetchall()
        return {str(row["slug"]) for row in rows}

    def _user_exists(self) -> bool:
        with get_connection(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM users
                WHERE id = ?
                LIMIT 1
                """,
                (self._user_id,),
            ).fetchone()
        return row is not None

    def _completed_count_for_lessons(
        self,
        course_slug: str,
        lesson_ids: Collection[str],
    ) -> int:
        """Return completed lessons that still belong to the current course."""
        if not lesson_ids:
            return 0

        current_lesson_ids = set(lesson_ids)
        completed_ids = self.completed_lessons(course_slug)
        return len(completed_ids & current_lesson_ids)

    def course_progress_percent(
        self,
        course_slug: str,
        lesson_ids: Collection[str],
    ) -> int:
        """Return completion percentage rounded to the nearest integer."""
        total_count = len(lesson_ids)
        if total_count <= 0:
            return 0

        completed_count = self._completed_count_for_lessons(course_slug, lesson_ids)
        return round(completed_count * 100 / total_count)

    def course_completed(
        self,
        course_slug: str,
        lesson_ids: Collection[str],
    ) -> bool:
        """Return whether every current lesson in the course is completed."""
        total_count = len(lesson_ids)
        if total_count <= 0:
            return False

        completed_count = self._completed_count_for_lessons(course_slug, lesson_ids)
        return completed_count == total_count

    def build_course_progress_view(
        self,
        course_slug: str,
        lessons: tuple,
        *,
        has_quiz: bool,
    ) -> CourseProgressView:
        """Build template-ready progress data and lesson status labels."""
        completed_ids = self.completed_lessons(course_slug)
        lesson_ids = tuple(lesson.id for lesson in lessons)
        total_count = len(lesson_ids)
        completed_count = self._completed_count_for_lessons(course_slug, lesson_ids)
        if total_count == 0:
            percent = 0
            is_completed = False
        else:
            percent = round(completed_count * 100 / total_count)
            is_completed = completed_count == total_count

        current_lesson_id: Optional[str] = None
        if not is_completed:
            for lesson in lessons:
                if lesson.id not in completed_ids:
                    current_lesson_id = lesson.id
                    break

        lesson_rows: list[LessonProgressRow] = []
        for lesson in lessons:
            if lesson.id in completed_ids:
                status = "completed"
                status_label = "Завершён"
            elif lesson.id == current_lesson_id:
                status = "current"
                status_label = "Текущий"
            else:
                status = "not_started"
                status_label = "Не открыт"
            lesson_rows.append(
                LessonProgressRow(
                    id=lesson.id,
                    title=lesson.title,
                    order=lesson.order,
                    status=status,
                    status_label=status_label,
                )
            )

        completion_message: Optional[str] = None
        if is_completed:
            if has_quiz:
                completion_message = "Можно пройти итоговый тест"
            else:
                completion_message = "Курс завершён"

        return CourseProgressView(
            percent=percent,
            completed_count=completed_count,
            total_count=total_count,
            is_completed=is_completed,
            completion_message=completion_message,
            lesson_rows=tuple(lesson_rows),
        )
