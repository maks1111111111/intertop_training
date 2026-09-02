"""Safe archive and restore lifecycle for admin courses."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.content.runtime import ContentRuntime
from app.content.runtime_loader import get_course
from app.content.runtime_manager import ContentRuntimeManager
from app.repositories.course_repository import CourseRepository
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_delete_service import _resolve_course_dir
from app.web.admin_course_edit_service import (
    AdminCourseEditError,
    _atomic_write_json,
    _load_course_json_payload,
)

_logger = logging.getLogger(__name__)

_PUBLISHED_STATUS = "published"
_ARCHIVED_STATUS = "archived"


@dataclass(frozen=True)
class AdminCourseLifecycleView:
    """Confirmation view for archiving one published course."""

    slug: str
    title: str
    lesson_count: int
    active_assignments_count: int
    can_archive: bool
    detail_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminCourseLifecycleResult:
    """Result of an archive or restore lifecycle action."""

    success: bool
    code: str
    message: str
    slug: str


class AdminCourseLifecycleService:
    """Archive and restore published courses while preserving learner history."""

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

    def get_archive_view(self, slug: str) -> Optional[AdminCourseLifecycleView]:
        """Build the archive confirmation view for one course slug."""
        normalized_slug = self._normalize_slug(slug)
        course = get_course(self._courses_dir, normalized_slug)
        if course is None:
            return None

        active_assignments_count = self._course_repository.count_active_enrollments(
            self._db_path,
            normalized_slug,
        )
        detail_url = f"/admin/courses/{normalized_slug}"
        return AdminCourseLifecycleView(
            slug=normalized_slug,
            title=course.title,
            lesson_count=len(course.lessons),
            active_assignments_count=active_assignments_count,
            can_archive=active_assignments_count == 0 and course.status == _PUBLISHED_STATUS,
            detail_url=detail_url,
            cancel_url=detail_url,
        )

    def archive_course(self, slug: str) -> AdminCourseLifecycleResult:
        """Archive one published course when no active assignments exist."""
        normalized_slug = self._normalize_slug(slug)
        view = self.get_archive_view(normalized_slug)
        if view is None:
            return AdminCourseLifecycleResult(
                success=False,
                code="not_found",
                message="Курс не найден.",
                slug=normalized_slug,
            )

        course = get_course(self._courses_dir, normalized_slug)
        assert course is not None

        if course.status == _ARCHIVED_STATUS:
            return AdminCourseLifecycleResult(
                success=False,
                code="already_archived",
                message="Курс уже находится в архиве.",
                slug=normalized_slug,
            )
        if course.status != _PUBLISHED_STATUS:
            return AdminCourseLifecycleResult(
                success=False,
                code="not_archivable",
                message="Курс нельзя архивировать в текущем состоянии.",
                slug=normalized_slug,
            )
        if view.active_assignments_count > 0:
            return AdminCourseLifecycleResult(
                success=False,
                code="active_assignments",
                message=(
                    "Курс нельзя архивировать, пока есть активные назначения."
                ),
                slug=normalized_slug,
            )

        course_json_path = _resolve_course_dir(self._courses_dir, normalized_slug) / "course.json"
        if not course_json_path.is_file():
            return AdminCourseLifecycleResult(
                success=False,
                code="not_found",
                message="Курс не найден.",
                slug=normalized_slug,
            )

        try:
            original_payload = _load_course_json_payload(course_json_path, normalized_slug)
        except AdminCourseEditError:
            return AdminCourseLifecycleResult(
                success=False,
                code="filesystem_read_failure",
                message="Не удалось загрузить метаданные курса.",
                slug=normalized_slug,
            )

        archived_payload = dict(original_payload)
        archived_payload["status"] = _ARCHIVED_STATUS

        try:
            _atomic_write_json(course_json_path, archived_payload)
        except OSError:
            _logger.exception(
                "Failed to archive course metadata on disk for slug=%s",
                normalized_slug,
            )
            return AdminCourseLifecycleResult(
                success=False,
                code="filesystem_write_failure",
                message="Не удалось сохранить статус архива курса.",
                slug=normalized_slug,
            )

        try:
            updated = self._course_repository.set_status(
                self._db_path,
                normalized_slug,
                _ARCHIVED_STATUS,
            )
            if not updated:
                self._restore_course_json(course_json_path, original_payload)
                return AdminCourseLifecycleResult(
                    success=False,
                    code="database_update_failure",
                    message="Не удалось обновить статус курса в базе данных.",
                    slug=normalized_slug,
                )
        except Exception:
            _logger.exception(
                "Failed to update archived course status in database for slug=%s",
                normalized_slug,
            )
            self._restore_course_json(course_json_path, original_payload)
            return AdminCourseLifecycleResult(
                success=False,
                code="database_update_failure",
                message="Не удалось обновить статус курса в базе данных.",
                slug=normalized_slug,
            )

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception:
            _logger.exception(
                "Archived course persisted but runtime refresh failed for slug=%s",
                normalized_slug,
            )
            return AdminCourseLifecycleResult(
                success=False,
                code="refresh_failure",
                message="Курс архивирован, но не удалось обновить каталог курсов.",
                slug=normalized_slug,
            )

        archived_course = get_course(self._courses_dir, normalized_slug)
        if (
            archived_course is None
            or archived_course.status != _ARCHIVED_STATUS
            or self._runtime.get_course(normalized_slug) is not None
        ):
            return AdminCourseLifecycleResult(
                success=False,
                code="refresh_failure",
                message="Курс архивирован, но не удалось обновить каталог курсов.",
                slug=normalized_slug,
            )

        return AdminCourseLifecycleResult(
            success=True,
            code="archived",
            message="Курс архивирован.",
            slug=normalized_slug,
        )

    def restore_course(self, slug: str) -> AdminCourseLifecycleResult:
        """Restore one archived course back to published status."""
        normalized_slug = self._normalize_slug(slug)
        course = get_course(self._courses_dir, normalized_slug)
        if course is None:
            return AdminCourseLifecycleResult(
                success=False,
                code="not_found",
                message="Курс не найден.",
                slug=normalized_slug,
            )

        if course.status == _PUBLISHED_STATUS:
            return AdminCourseLifecycleResult(
                success=False,
                code="already_published",
                message="Курс уже опубликован.",
                slug=normalized_slug,
            )
        if course.status != _ARCHIVED_STATUS:
            return AdminCourseLifecycleResult(
                success=False,
                code="not_restorable",
                message="Курс нельзя восстановить в текущем состоянии.",
                slug=normalized_slug,
            )

        course_json_path = _resolve_course_dir(self._courses_dir, normalized_slug) / "course.json"
        if not course_json_path.is_file():
            return AdminCourseLifecycleResult(
                success=False,
                code="not_found",
                message="Курс не найден.",
                slug=normalized_slug,
            )

        try:
            original_payload = _load_course_json_payload(course_json_path, normalized_slug)
        except AdminCourseEditError:
            return AdminCourseLifecycleResult(
                success=False,
                code="filesystem_read_failure",
                message="Не удалось загрузить метаданные курса.",
                slug=normalized_slug,
            )

        published_payload = dict(original_payload)
        published_payload["status"] = _PUBLISHED_STATUS

        try:
            _atomic_write_json(course_json_path, published_payload)
        except OSError:
            _logger.exception(
                "Failed to restore course metadata on disk for slug=%s",
                normalized_slug,
            )
            return AdminCourseLifecycleResult(
                success=False,
                code="filesystem_write_failure",
                message="Не удалось восстановить статус курса.",
                slug=normalized_slug,
            )

        try:
            updated = self._course_repository.set_status(
                self._db_path,
                normalized_slug,
                _PUBLISHED_STATUS,
            )
            if not updated:
                self._restore_course_json(course_json_path, original_payload)
                return AdminCourseLifecycleResult(
                    success=False,
                    code="database_update_failure",
                    message="Не удалось обновить статус курса в базе данных.",
                    slug=normalized_slug,
                )
        except Exception:
            _logger.exception(
                "Failed to update restored course status in database for slug=%s",
                normalized_slug,
            )
            self._restore_course_json(course_json_path, original_payload)
            return AdminCourseLifecycleResult(
                success=False,
                code="database_update_failure",
                message="Не удалось обновить статус курса в базе данных.",
                slug=normalized_slug,
            )

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception:
            _logger.exception(
                "Restored course persisted but runtime refresh failed for slug=%s",
                normalized_slug,
            )
            return AdminCourseLifecycleResult(
                success=False,
                code="refresh_failure",
                message="Курс восстановлен, но не удалось обновить каталог курсов.",
                slug=normalized_slug,
            )

        restored_course = get_course(self._courses_dir, normalized_slug)
        runtime_course = self._runtime.get_course(normalized_slug)
        if (
            restored_course is None
            or restored_course.status != _PUBLISHED_STATUS
            or runtime_course is None
        ):
            return AdminCourseLifecycleResult(
                success=False,
                code="refresh_failure",
                message="Курс восстановлен, но не удалось обновить каталог курсов.",
                slug=normalized_slug,
            )

        return AdminCourseLifecycleResult(
            success=True,
            code="restored",
            message="Курс восстановлен.",
            slug=normalized_slug,
        )

    def _restore_course_json(self, course_json_path: Path, payload: dict) -> None:
        try:
            _atomic_write_json(course_json_path, payload)
        except OSError:
            _logger.exception(
                "Failed to roll back course metadata at %s",
                course_json_path,
            )

    def _normalize_slug(self, slug: str) -> str:
        normalized = str(slug or "").strip()
        if not normalized:
            raise AdminCourseEditError("Некорректный идентификатор курса.")
        _resolve_course_dir(self._courses_dir, normalized)
        return normalized
