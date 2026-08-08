"""SQLite-backed lesson progress for the read-only Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Optional

from app.database.db import get_connection

WEB_DEMO_USER_ID = "web-demo-user"


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


class WebProgressService:
    """Persist and read Web lesson completion in SQLite."""

    def __init__(
        self,
        db_path: Path,
        user_id: str = WEB_DEMO_USER_ID,
    ) -> None:
        self._db_path = db_path
        self._user_id = user_id

    def mark_lesson_completed(self, course_slug: str, lesson_id: str) -> None:
        """Record one completed lesson without creating duplicates."""
        with get_connection(self._db_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO web_lesson_progress (
                    user_id,
                    course_slug,
                    lesson_id
                )
                VALUES (?, ?, ?)
                """,
                (self._user_id, course_slug, lesson_id),
            )
            connection.commit()

    def is_lesson_completed(self, course_slug: str, lesson_id: str) -> bool:
        """Return whether the lesson is marked completed for the current user."""
        with get_connection(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM web_lesson_progress
                WHERE user_id = ?
                  AND course_slug = ?
                  AND lesson_id = ?
                LIMIT 1
                """,
                (self._user_id, course_slug, lesson_id),
            ).fetchone()
        return row is not None

    def completed_lessons(self, course_slug: str) -> set[str]:
        """Return lesson ids completed by the current user in one course."""
        with get_connection(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT lesson_id
                FROM web_lesson_progress
                WHERE user_id = ?
                  AND course_slug = ?
                ORDER BY lesson_id
                """,
                (self._user_id, course_slug),
            ).fetchall()
        return {str(row["lesson_id"]) for row in rows}

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
