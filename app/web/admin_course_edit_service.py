"""Admin course metadata editing for the Web UI."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.content.contract import COURSE_JSON_FILENAME
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_service import AdminSelectOption

_logger = logging.getLogger(__name__)

_SUPPORTED_COURSE_LANGUAGES = frozenset({"ru", "kk", "en"})

PERSISTED_LANGUAGE_OPTIONS: tuple[AdminSelectOption, ...] = (
    AdminSelectOption("ru", "Русский"),
    AdminSelectOption("kk", "Қазақша"),
    AdminSelectOption("en", "English"),
)


class AdminCourseEditError(Exception):
    """Raised when admin course metadata cannot be edited safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminCourseEditView:
    """View model for the admin course metadata edit form."""

    slug: str
    title: str
    description: str
    language: str
    language_options: tuple[AdminSelectOption, ...]
    detail_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminCourseEditRequest:
    """Validated input for updating one course's metadata."""

    slug: str
    title: str
    description: str
    language: str


@dataclass(frozen=True)
class AdminCourseEditResult:
    """Result of a successful course metadata update."""

    slug: str


def _resolve_course_json_path(courses_dir: Path, slug: str) -> Path:
    """Resolve ``course.json`` for ``slug`` without escaping ``courses_dir``."""
    normalized = str(slug or "").strip()
    if not normalized:
        raise AdminCourseEditError("Некорректный идентификатор курса.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminCourseEditError("Некорректный идентификатор курса.")
    if ".." in Path(normalized).parts:
        raise AdminCourseEditError("Некорректный идентификатор курса.")

    courses_root = courses_dir.resolve()
    course_dir = (courses_dir / normalized).resolve()
    if os.path.commonpath([str(course_dir), str(courses_root)]) != str(courses_root):
        raise AdminCourseEditError("Некорректный идентификатор курса.")
    if course_dir.parent != courses_root:
        raise AdminCourseEditError("Некорректный идентификатор курса.")

    course_json = course_dir / COURSE_JSON_FILENAME
    if not course_json.is_file():
        raise AdminCourseEditError("Курс не найден.")
    return course_json


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using a temporary file in the same directory."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
        os.replace(temp_path, path)
    except OSError:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _validate_title(raw_title: str) -> str:
    title = str(raw_title or "").strip()
    if not title:
        raise AdminCourseEditError("Название курса обязательно.")
    return title


def _validate_description(raw_description: str) -> str:
    return str(raw_description or "").strip()


def _validate_language(raw_language: str) -> str:
    language = str(raw_language or "").strip().lower()
    if language not in _SUPPORTED_COURSE_LANGUAGES:
        raise AdminCourseEditError("Выберите поддерживаемый язык курса.")
    return language


def _load_course_json_payload(course_json_path: Path, slug: str) -> dict:
    """Load existing ``course.json`` metadata without exposing parser details."""
    try:
        raw = course_json_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.exception("Failed to read course metadata for slug=%s", slug)
        raise AdminCourseEditError("Не удалось загрузить метаданные курса.") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.exception("Failed to parse course metadata for slug=%s", slug)
        raise AdminCourseEditError("Не удалось загрузить метаданные курса.") from exc

    if not isinstance(payload, dict):
        raise AdminCourseEditError("Не удалось загрузить метаданные курса.")
    return payload


class AdminCourseEditService:
    """Update course metadata in ``course.json`` and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_edit_view(self, slug: str) -> Optional[AdminCourseEditView]:
        """Return the edit form view for one course, or ``None`` if missing."""
        course = self._runtime.get_course(slug)
        if course is None:
            return None

        return AdminCourseEditView(
            slug=course.slug,
            title=course.title,
            description=course.description,
            language=course.language or "ru",
            language_options=PERSISTED_LANGUAGE_OPTIONS,
            detail_url=f"/admin/courses/{course.slug}",
            cancel_url=f"/admin/courses/{course.slug}",
        )

    def update_metadata(self, request: AdminCourseEditRequest) -> AdminCourseEditResult:
        """Validate, persist, and refresh one course's metadata."""
        title = _validate_title(request.title)
        description = _validate_description(request.description)
        language = _validate_language(request.language)

        course_json_path = _resolve_course_json_path(self._courses_dir, request.slug)
        payload = _load_course_json_payload(course_json_path, request.slug)

        payload["title"] = title
        payload["description"] = description
        payload["language"] = language

        try:
            _atomic_write_json(course_json_path, payload)
        except OSError as exc:
            _logger.exception("Failed to write course metadata for slug=%s", request.slug)
            raise AdminCourseEditError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Course metadata saved but runtime refresh failed for slug=%s",
                request.slug,
            )
            raise AdminCourseEditError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc

        return AdminCourseEditResult(slug=request.slug)
