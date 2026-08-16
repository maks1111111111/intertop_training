"""Manual admin course creation for the Web UI."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.content.contract import COURSE_JSON_FILENAME
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import (
    AdminCourseEditError,
    PERSISTED_LANGUAGE_OPTIONS,
    _atomic_write_json,
    _validate_description,
    _validate_language,
    _validate_title,
)
from app.web.admin_service import AdminSelectOption

_logger = logging.getLogger(__name__)


class AdminManualCourseCreateError(Exception):
    """Raised when a manual course cannot be created safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminManualCourseCreateView:
    """View model for the manual course creation form."""

    language_options: tuple[AdminSelectOption, ...]
    back_url: str


@dataclass(frozen=True)
class AdminManualCourseCreateRequest:
    """Validated input for creating one course manually."""

    title: str
    description: str
    language: str


@dataclass(frozen=True)
class AdminManualCourseCreateResult:
    """Result of a successful manual course creation."""

    slug: str
    detail_url: str


def _generate_unique_slug(courses_dir: Path) -> str:
    """Return a unique opaque course slug that does not collide on disk."""
    courses_root = courses_dir.resolve()
    for _ in range(32):
        slug = f"course-{uuid.uuid4().hex[:12]}"
        candidate = (courses_dir / slug).resolve()
        if os.path.commonpath([str(candidate), str(courses_root)]) != str(courses_root):
            continue
        if candidate.parent != courses_root:
            continue
        if not candidate.exists():
            return slug
    raise AdminManualCourseCreateError(
        "Не удалось создать курс. Попробуйте ещё раз."
    )


def _safe_remove_course_dir(courses_dir: Path, course_dir: Path) -> None:
    """Remove ``course_dir`` only when it is a direct child of ``courses_dir``."""
    resolved_root = courses_dir.resolve()
    resolved_course = course_dir.resolve()
    if os.path.commonpath([str(resolved_course), str(resolved_root)]) != str(resolved_root):
        return
    if resolved_course.parent != resolved_root:
        return
    if not resolved_course.is_dir():
        return
    shutil.rmtree(resolved_course, ignore_errors=True)


class AdminManualCourseCreateService:
    """Create an empty course directory and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_create_view(self) -> AdminManualCourseCreateView:
        """Return the static view model for the manual course creation form."""
        return AdminManualCourseCreateView(
            language_options=PERSISTED_LANGUAGE_OPTIONS,
            back_url="/admin/courses/new",
        )

    def create_course(
        self, request: AdminManualCourseCreateRequest
    ) -> AdminManualCourseCreateResult:
        """Create a new empty course and refresh runtime."""
        title = _validate_title_for_manual(request.title)
        description = _validate_description(request.description)
        language = _validate_language_for_manual(request.language)

        slug = _generate_unique_slug(self._courses_dir)
        course_dir = (self._courses_dir / slug).resolve()

        try:
            course_dir.mkdir(parents=False, exist_ok=False)
        except OSError as exc:
            _logger.exception("Failed to create course directory for manual create")
            raise AdminManualCourseCreateError(
                "Не удалось создать курс. Попробуйте ещё раз."
            ) from exc

        course_json_path = course_dir / COURSE_JSON_FILENAME
        payload = {
            "title": title,
            "description": description,
            "language": language,
            "slug": slug,
        }

        try:
            _atomic_write_json(course_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to write course metadata for manual create slug=%s", slug
            )
            _safe_remove_course_dir(self._courses_dir, course_dir)
            raise AdminManualCourseCreateError(
                "Не удалось создать курс. Попробуйте ещё раз."
            ) from exc

        RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()

        return AdminManualCourseCreateResult(
            slug=slug,
            detail_url=f"/admin/courses/{slug}",
        )


def _validate_title_for_manual(raw_title: str) -> str:
    try:
        return _validate_title(raw_title)
    except AdminCourseEditError as exc:
        raise AdminManualCourseCreateError(exc.message) from exc


def _validate_language_for_manual(raw_language: str) -> str:
    try:
        return _validate_language(raw_language)
    except AdminCourseEditError as exc:
        raise AdminManualCourseCreateError(exc.message) from exc
