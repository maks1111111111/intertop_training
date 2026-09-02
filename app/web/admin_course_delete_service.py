"""Safe permanent deletion of unused admin courses for the Web UI."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.database.db import get_connection
from app.repositories.course_repository import CourseRepository
from app.services.runtime_refresh_service import RuntimeRefreshService

_logger = logging.getLogger(__name__)


class AdminCourseDeleteError(Exception):
    """Raised when a course slug cannot be resolved safely for deletion."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminCourseDeleteHistoryCounts:
    """Learner history counts that block permanent course deletion."""

    enrollments_count: int
    quiz_attempts_count: int
    practical_task_attempts_count: int
    web_lesson_progress_count: int

    @property
    def total(self) -> int:
        return (
            self.enrollments_count
            + self.quiz_attempts_count
            + self.practical_task_attempts_count
            + self.web_lesson_progress_count
        )


@dataclass(frozen=True)
class AdminCourseDeleteView:
    """Confirmation view for deleting one unused course."""

    slug: str
    title: str
    lesson_count: int
    can_delete: bool
    history: AdminCourseDeleteHistoryCounts
    detail_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminCourseDeleteResult:
    """Result of attempting to delete one course permanently."""

    success: bool
    code: str
    message: str
    slug: str


def _resolve_course_dir(courses_dir: Path, slug: str) -> Path:
    """Resolve a course directory for ``slug`` without escaping ``courses_dir``."""
    normalized = str(slug or "").strip()
    if not normalized:
        raise AdminCourseDeleteError("Некорректный идентификатор курса.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminCourseDeleteError("Некорректный идентификатор курса.")
    if ".." in Path(normalized).parts:
        raise AdminCourseDeleteError("Некорректный идентификатор курса.")

    courses_root = courses_dir.resolve()
    course_dir = (courses_dir / normalized).resolve()
    if os.path.commonpath([str(course_dir), str(courses_root)]) != str(courses_root):
        raise AdminCourseDeleteError("Некорректный идентификатор курса.")
    if course_dir.parent != courses_root:
        raise AdminCourseDeleteError("Некорректный идентификатор курса.")
    return course_dir


def _count_course_history(db_path: Path, *, course_slug: str, course_id: Optional[int]) -> AdminCourseDeleteHistoryCounts:
    """Return learner history counts that block deletion for one course."""
    enrollments_count = 0
    quiz_attempts_count = 0
    practical_task_attempts_count = 0
    web_lesson_progress_count = 0

    with get_connection(db_path) as connection:
        if course_id is not None:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM enrollments
                WHERE course_id = ?
                """,
                (course_id,),
            ).fetchone()
            enrollments_count = int(row["count"])

        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM quiz_attempts
            WHERE course_slug = ?
            """,
            (course_slug,),
        ).fetchone()
        quiz_attempts_count = int(row["count"])

        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM practical_task_attempts
            WHERE course_slug = ?
            """,
            (course_slug,),
        ).fetchone()
        practical_task_attempts_count = int(row["count"])

        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM web_lesson_progress
            WHERE course_slug = ?
            """,
            (course_slug,),
        ).fetchone()
        web_lesson_progress_count = int(row["count"])

    return AdminCourseDeleteHistoryCounts(
        enrollments_count=enrollments_count,
        quiz_attempts_count=quiz_attempts_count,
        practical_task_attempts_count=practical_task_attempts_count,
        web_lesson_progress_count=web_lesson_progress_count,
    )


class AdminCourseDeleteService:
    """Delete unused published courses from disk and refresh runtime/database."""

    def __init__(
        self,
        courses_dir: Path,
        runtime: ContentRuntime,
        db_path: Path,
        *,
        course_repository: Optional[CourseRepository] = None,
    ) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime
        self._db_path = db_path
        self._course_repository = course_repository or CourseRepository()

    def get_delete_view(self, slug: str) -> Optional[AdminCourseDeleteView]:
        """Build the delete confirmation view for one course slug."""
        normalized_slug = self._normalize_slug(slug)
        course = self._runtime.get_course(normalized_slug)
        if course is None:
            return None

        course_dir = _resolve_course_dir(self._courses_dir, normalized_slug)
        if not course_dir.is_dir():
            return None

        course_row = self._course_repository.get_by_slug(self._db_path, normalized_slug)
        course_id = int(course_row["id"]) if course_row is not None else None
        history = _count_course_history(
            self._db_path,
            course_slug=normalized_slug,
            course_id=course_id,
        )

        detail_url = f"/admin/courses/{normalized_slug}"
        return AdminCourseDeleteView(
            slug=normalized_slug,
            title=course.title,
            lesson_count=len(course.lessons),
            can_delete=history.total == 0,
            history=history,
            detail_url=detail_url,
            cancel_url=detail_url,
        )

    def delete_course(self, slug: str) -> AdminCourseDeleteResult:
        """Permanently delete one unused course when learner history is absent."""
        normalized_slug = self._normalize_slug(slug)
        view = self.get_delete_view(normalized_slug)
        if view is None:
            return AdminCourseDeleteResult(
                success=False,
                code="not_found",
                message="Курс не найден.",
                slug=normalized_slug,
            )
        if not view.can_delete:
            return AdminCourseDeleteResult(
                success=False,
                code="course_has_history",
                message=(
                    "Курс использовался в обучении и не может быть удалён "
                    "без потери истории."
                ),
                slug=normalized_slug,
            )

        course_dir = _resolve_course_dir(self._courses_dir, normalized_slug)
        try:
            shutil.rmtree(course_dir)
        except OSError:
            _logger.exception(
                "Failed to delete course directory for slug=%s",
                normalized_slug,
            )
            return AdminCourseDeleteResult(
                success=False,
                code="filesystem_delete_failure",
                message="Не удалось удалить файлы курса.",
                slug=normalized_slug,
            )

        if course_dir.exists():
            return AdminCourseDeleteResult(
                success=False,
                code="filesystem_delete_failure",
                message="Не удалось удалить файлы курса.",
                slug=normalized_slug,
            )

        try:
            self._course_repository.delete_by_slug(
                self._db_path,
                normalized_slug,
            )
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception:
            _logger.exception(
                "Failed to finalize course deletion for slug=%s",
                normalized_slug,
            )
            return AdminCourseDeleteResult(
                success=False,
                code="delete_finalize_failure",
                message="Не удалось завершить удаление курса.",
                slug=normalized_slug,
            )

        return AdminCourseDeleteResult(
            success=True,
            code="deleted",
            message="Курс удалён.",
            slug=normalized_slug,
        )

    def _normalize_slug(self, slug: str) -> str:
        try:
            course_dir = _resolve_course_dir(self._courses_dir, slug)
        except AdminCourseDeleteError as exc:
            raise AdminCourseDeleteError(exc.message) from exc
        if not course_dir.exists() and not str(slug or "").strip():
            raise AdminCourseDeleteError("Некорректный идентификатор курса.")
        return str(slug or "").strip()
