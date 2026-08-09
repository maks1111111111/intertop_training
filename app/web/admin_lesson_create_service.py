"""Admin lesson creation for the Web UI."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.content.contract import LESSON_JSON_FILENAME
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json
from app.web.admin_lesson_edit_service import _resolve_course_dir

_logger = logging.getLogger(__name__)

_LESSON_DIR_PATTERN = re.compile(r"^lesson_(\d+)$")
_DEFAULT_LESSON_TITLE = "Новый урок"


class AdminLessonCreateError(Exception):
    """Raised when a new lesson cannot be created safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminLessonCreateResult:
    """Result of a successful lesson creation."""

    slug: str
    lesson_id: str
    edit_url: str


def _next_lesson_id_and_order(course_dir: Path) -> tuple[str, int]:
    """Return the next ``lesson_XX`` id and order for one course directory."""
    max_suffix = 0
    max_order = 0

    for entry in course_dir.iterdir():
        if not entry.is_dir():
            continue

        match = _LESSON_DIR_PATTERN.match(entry.name)
        if match is not None:
            max_suffix = max(max_suffix, int(match.group(1)))

        lesson_json = entry / LESSON_JSON_FILENAME
        if not lesson_json.is_file():
            continue

        try:
            payload = json.loads(lesson_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue

        if not isinstance(payload, dict):
            continue

        try:
            order = int(payload.get("order", 0))
        except (TypeError, ValueError):
            continue
        max_order = max(max_order, order)

    next_suffix = max_suffix + 1 if max_suffix > 0 else 1
    next_order = max_order + 1 if max_order > 0 else 1
    return f"lesson_{next_suffix:02d}", next_order


def _build_initial_lesson_payload(order: int) -> dict:
    """Return a minimal runtime-compatible ``lesson.json`` payload."""
    return {
        "title": _DEFAULT_LESSON_TITLE,
        "order": order,
        "description": "",
        "practical_task": "",
        "checklist": [],
        "common_mistakes": [],
        "key_takeaways": [],
        "application_tips": [],
    }


def _safe_remove_lesson_dir(course_dir: Path, lesson_dir: Path) -> None:
    """Remove ``lesson_dir`` only when it is a direct child of ``course_dir``."""
    resolved_course = course_dir.resolve()
    resolved_lesson = lesson_dir.resolve()
    if os.path.commonpath([str(resolved_lesson), str(resolved_course)]) != str(
        resolved_course
    ):
        return
    if resolved_lesson.parent != resolved_course:
        return
    if not resolved_lesson.is_dir():
        return
    shutil.rmtree(resolved_lesson, ignore_errors=True)


class AdminLessonCreateService:
    """Create a new lesson directory and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def create_lesson(self, slug: str) -> AdminLessonCreateResult:
        """Create a new lesson for one course and refresh runtime."""
        course_dir = _resolve_course_dir(self._courses_dir, slug)
        lesson_id, order = _next_lesson_id_and_order(course_dir)
        lesson_dir = course_dir / lesson_id

        if lesson_dir.exists():
            raise AdminLessonCreateError(
                "Не удалось создать урок. Попробуйте обновить страницу и повторить."
            )

        try:
            lesson_dir.mkdir(parents=False, exist_ok=False)
        except OSError as exc:
            _logger.exception("Failed to create lesson directory for slug=%s", slug)
            raise AdminLessonCreateError(
                "Не удалось создать урок. Попробуйте ещё раз."
            ) from exc

        lesson_json_path = lesson_dir / LESSON_JSON_FILENAME
        payload = _build_initial_lesson_payload(order)

        try:
            _atomic_write_json(lesson_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to write initial lesson metadata for slug=%s lesson_id=%s",
                slug,
                lesson_id,
            )
            _safe_remove_lesson_dir(course_dir, lesson_dir)
            raise AdminLessonCreateError(
                "Не удалось создать урок. Попробуйте ещё раз."
            ) from exc

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Lesson created but runtime refresh failed for slug=%s lesson_id=%s",
                slug,
                lesson_id,
            )
            raise AdminLessonCreateError(
                "Урок создан, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc

        return AdminLessonCreateResult(
            slug=slug,
            lesson_id=lesson_id,
            edit_url=f"/admin/courses/{slug}/lessons/{lesson_id}/edit",
        )
