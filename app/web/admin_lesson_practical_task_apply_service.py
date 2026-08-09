"""Apply AI-generated lesson practical-task previews to lesson.json."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json
from app.web.admin_lesson_edit_service import (
    AdminLessonEditError,
    _resolve_lesson_json_path,
)
from app.web.admin_lesson_practical_task_preview_store import (
    AdminLessonPracticalTaskPreviewStore,
    AdminLessonPracticalTaskPreviewStoreError,
    StoredPreviewPracticalTask,
    _validate_preview_id,
)

_logger = logging.getLogger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class AdminLessonPracticalTaskApplyError(Exception):
    """Raised when a practical-task preview cannot be applied safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminLessonPracticalTaskApplyRequest:
    slug: str
    lesson_id: str
    preview_id: str


@dataclass(frozen=True)
class AdminLessonPracticalTaskApplyResult:
    slug: str
    lesson_id: str


def _validate_identifier(raw: str, *, not_found_message: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise AdminLessonPracticalTaskApplyError(not_found_message)
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminLessonPracticalTaskApplyError(not_found_message)
    if not _IDENTIFIER_PATTERN.match(normalized):
        raise AdminLessonPracticalTaskApplyError(not_found_message)
    return normalized


def _load_lesson_json_payload(lesson_json_path) -> dict:
    try:
        raw = lesson_json_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.exception("Failed to read lesson.json for apply")
        raise AdminLessonPracticalTaskApplyError(
            "Не удалось загрузить данные урока."
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.exception("Malformed lesson.json for apply")
        raise AdminLessonPracticalTaskApplyError(
            "Не удалось загрузить данные урока."
        ) from exc

    if not isinstance(payload, dict):
        raise AdminLessonPracticalTaskApplyError("Не удалось загрузить данные урока.")
    return payload


def _serialize_structured_practical_task(task: StoredPreviewPracticalTask) -> dict:
    serialized = {
        "title": task.title,
        "description": task.description,
        "expected_result": task.expected_result,
    }
    if task.estimated_minutes is not None:
        serialized["estimated_minutes"] = task.estimated_minutes
    return serialized


class AdminLessonPracticalTaskApplyService:
    """Apply an AI preview practical task to an existing lesson."""

    def __init__(
        self,
        courses_dir,
        runtime: ContentRuntime,
        preview_store: AdminLessonPracticalTaskPreviewStore,
    ) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime
        self._preview_store = preview_store

    def apply_preview(
        self,
        request: AdminLessonPracticalTaskApplyRequest,
    ) -> AdminLessonPracticalTaskApplyResult:
        """Validate preview state and persist the practical task to ``lesson.json``."""
        slug = _validate_identifier(
            request.slug,
            not_found_message="Некорректный идентификатор курса.",
        )
        lesson_id = _validate_identifier(
            request.lesson_id,
            not_found_message="Некорректный идентификатор урока.",
        )

        try:
            preview_id = _validate_preview_id(request.preview_id)
        except AdminLessonPracticalTaskPreviewStoreError as exc:
            raise AdminLessonPracticalTaskApplyError(exc.message) from exc

        record = self._preview_store.get(preview_id)
        if record is None:
            raise AdminLessonPracticalTaskApplyError(
                "Предпросмотр задания недоступен. Сгенерируйте задание снова."
            )
        if record.slug != slug or record.lesson_id != lesson_id:
            raise AdminLessonPracticalTaskApplyError(
                "Предпросмотр задания недоступен. Сгенерируйте задание снова."
            )

        task = record.task
        if not task.title.strip() or not task.description.strip():
            raise AdminLessonPracticalTaskApplyError(
                "Не удалось применить практическое задание."
            )
        if not task.expected_result.strip():
            raise AdminLessonPracticalTaskApplyError(
                "Не удалось применить практическое задание."
            )

        try:
            lesson_json_path = _resolve_lesson_json_path(
                self._courses_dir,
                slug,
                lesson_id,
            )
        except AdminLessonEditError as exc:
            raise AdminLessonPracticalTaskApplyError(exc.message) from exc

        try:
            payload = _load_lesson_json_payload(lesson_json_path)
        except AdminLessonPracticalTaskApplyError:
            raise

        payload["structured_practical_task"] = _serialize_structured_practical_task(task)
        payload["practical_task"] = task.description

        try:
            _atomic_write_json(lesson_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to apply lesson practical-task preview slug=%s lesson=%s",
                slug,
                lesson_id,
            )
            raise AdminLessonPracticalTaskApplyError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        self._preview_store.consume(preview_id)
        self._refresh_runtime(slug)
        return AdminLessonPracticalTaskApplyResult(slug=slug, lesson_id=lesson_id)

    def _refresh_runtime(self, slug: str) -> None:
        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Applied practical-task preview but runtime refresh failed slug=%s",
                slug,
            )
            raise AdminLessonPracticalTaskApplyError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc
