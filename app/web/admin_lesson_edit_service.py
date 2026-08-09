"""Admin lesson editing for the Web UI."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.content.contract import COURSE_JSON_FILENAME, LESSON_JSON_FILENAME
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json

_logger = logging.getLogger(__name__)


class AdminLessonEditError(Exception):
    """Raised when admin lesson content cannot be edited safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminLessonEditView:
    """View model for the admin lesson edit form."""

    slug: str
    lesson_id: str
    course_title: str
    lesson_order: int
    title: str
    description: str
    practical_task: str
    checklist_text: str
    key_takeaways_text: str
    application_tips_text: str
    detail_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminLessonEditRequest:
    """Validated input for updating one lesson."""

    slug: str
    lesson_id: str
    title: str
    description: str
    practical_task: str
    checklist: list[str]
    key_takeaways: list[str]
    application_tips: list[str]


@dataclass(frozen=True)
class AdminLessonEditResult:
    """Result of a successful lesson update."""

    slug: str
    lesson_id: str


def _validate_identifier(raw: str, *, not_found_message: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise AdminLessonEditError(not_found_message)
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminLessonEditError(not_found_message)
    if ".." in Path(normalized).parts:
        raise AdminLessonEditError(not_found_message)
    return normalized


def _resolve_course_dir(courses_dir: Path, slug: str) -> Path:
    """Resolve a course directory for ``slug`` without escaping ``courses_dir``."""
    normalized = _validate_identifier(slug, not_found_message="Некорректный идентификатор курса.")

    courses_root = courses_dir.resolve()
    course_dir = (courses_dir / normalized).resolve()
    if os.path.commonpath([str(course_dir), str(courses_root)]) != str(courses_root):
        raise AdminLessonEditError("Некорректный идентификатор курса.")
    if course_dir.parent != courses_root:
        raise AdminLessonEditError("Некорректный идентификатор курса.")

    course_json = course_dir / COURSE_JSON_FILENAME
    if not course_json.is_file():
        raise AdminLessonEditError("Курс не найден.")
    return course_dir


def _resolve_lesson_json_path(courses_dir: Path, slug: str, lesson_id: str) -> Path:
    """Resolve ``lesson.json`` for one lesson without escaping the course directory."""
    course_dir = _resolve_course_dir(courses_dir, slug)
    normalized_lesson_id = _validate_identifier(
        lesson_id,
        not_found_message="Некорректный идентификатор урока.",
    )

    lesson_dir = (course_dir / normalized_lesson_id).resolve()
    if os.path.commonpath([str(lesson_dir), str(course_dir.resolve())]) != str(
        course_dir.resolve()
    ):
        raise AdminLessonEditError("Некорректный идентификатор урока.")
    if lesson_dir.parent != course_dir.resolve():
        raise AdminLessonEditError("Некорректный идентификатор урока.")

    lesson_json = lesson_dir / LESSON_JSON_FILENAME
    if not lesson_json.is_file():
        raise AdminLessonEditError("Урок не найден.")
    return lesson_json


def _validate_title(raw_title: str) -> str:
    title = str(raw_title or "").strip()
    if not title:
        raise AdminLessonEditError("Название урока обязательно.")
    return title


def _validate_description(raw_description: str) -> str:
    return str(raw_description or "")


def _validate_practical_task(raw_practical_task: str) -> str:
    return str(raw_practical_task or "")


def _parse_multiline_list(raw: str) -> list[str]:
    items: list[str] = []
    for line in str(raw or "").splitlines():
        trimmed = line.strip()
        if trimmed:
            items.append(trimmed)
    return items


def _list_to_text(items: tuple[str, ...]) -> str:
    return "\n".join(items)


def _load_lesson_json_payload(lesson_json_path: Path, slug: str, lesson_id: str) -> dict:
    """Load existing ``lesson.json`` metadata without exposing parser details."""
    try:
        raw = lesson_json_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.exception(
            "Failed to read lesson metadata for slug=%s lesson_id=%s",
            slug,
            lesson_id,
        )
        raise AdminLessonEditError("Не удалось загрузить данные урока.") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.exception(
            "Failed to parse lesson metadata for slug=%s lesson_id=%s",
            slug,
            lesson_id,
        )
        raise AdminLessonEditError("Не удалось загрузить данные урока.") from exc

    if not isinstance(payload, dict):
        raise AdminLessonEditError("Не удалось загрузить данные урока.")
    return payload


class AdminLessonEditService:
    """Update lesson content in ``lesson.json`` and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_edit_view(self, slug: str, lesson_id: str) -> Optional[AdminLessonEditView]:
        """Return the edit form view for one lesson, or ``None`` if missing."""
        course = self._runtime.get_course(slug)
        if course is None:
            return None

        lesson = None
        for candidate in course.lessons:
            if candidate.path.name == lesson_id:
                lesson = candidate
                break
        if lesson is None:
            return None

        return AdminLessonEditView(
            slug=course.slug,
            lesson_id=lesson.path.name,
            course_title=course.title,
            lesson_order=lesson.number,
            title=lesson.title,
            description=lesson.description,
            practical_task=lesson.practical_task,
            checklist_text=_list_to_text(lesson.checklist),
            key_takeaways_text=_list_to_text(lesson.key_takeaways),
            application_tips_text=_list_to_text(lesson.application_tips),
            detail_url=f"/admin/courses/{course.slug}",
            cancel_url=f"/admin/courses/{course.slug}",
        )

    def update_lesson(self, request: AdminLessonEditRequest) -> AdminLessonEditResult:
        """Validate, persist, and refresh one lesson."""
        title = _validate_title(request.title)
        description = _validate_description(request.description)
        practical_task = _validate_practical_task(request.practical_task)
        checklist = list(request.checklist)
        key_takeaways = list(request.key_takeaways)
        application_tips = list(request.application_tips)

        lesson_json_path = _resolve_lesson_json_path(
            self._courses_dir,
            request.slug,
            request.lesson_id,
        )
        payload = _load_lesson_json_payload(
            lesson_json_path,
            request.slug,
            request.lesson_id,
        )

        payload["title"] = title
        payload["description"] = description
        payload["practical_task"] = practical_task
        payload["checklist"] = checklist
        payload["key_takeaways"] = key_takeaways
        payload["application_tips"] = application_tips

        try:
            _atomic_write_json(lesson_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to write lesson metadata for slug=%s lesson_id=%s",
                request.slug,
                request.lesson_id,
            )
            raise AdminLessonEditError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Lesson saved but runtime refresh failed for slug=%s lesson_id=%s",
                request.slug,
                request.lesson_id,
            )
            raise AdminLessonEditError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc

        return AdminLessonEditResult(slug=request.slug, lesson_id=request.lesson_id)
