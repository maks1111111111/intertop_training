"""Admin quiz creation for courses without an existing final test."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.content.contract import COURSE_JSON_FILENAME, QUIZ_JSON_FILENAME
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json

_logger = logging.getLogger(__name__)

_DEFAULT_QUIZ_TITLE = "Итоговый тест"
_DEFAULT_PASSING_SCORE = 80


class AdminQuizCreateError(Exception):
    """Raised when a course quiz cannot be created safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminQuizCreateResult:
    """Result of a successful quiz creation."""

    slug: str
    edit_url: str


def _resolve_course_dir_for_quiz_create(courses_dir: Path, slug: str) -> Path:
    """Resolve a course directory for quiz creation without escaping ``courses_dir``."""
    normalized = str(slug or "").strip()
    if not normalized:
        raise AdminQuizCreateError("Некорректный идентификатор курса.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminQuizCreateError("Некорректный идентификатор курса.")
    if ".." in Path(normalized).parts:
        raise AdminQuizCreateError("Некорректный идентификатор курса.")

    courses_root = courses_dir.resolve()
    course_dir = (courses_dir / normalized).resolve()
    if os.path.commonpath([str(course_dir), str(courses_root)]) != str(courses_root):
        raise AdminQuizCreateError("Некорректный идентификатор курса.")
    if course_dir.parent != courses_root:
        raise AdminQuizCreateError("Некорректный идентификатор курса.")

    course_json = course_dir / COURSE_JSON_FILENAME
    if not course_json.is_file():
        raise AdminQuizCreateError("Курс не найден.")
    return course_dir


def _build_initial_quiz_payload(slug: str) -> dict:
    """Return a minimal runtime-compatible ``quiz.json`` payload."""
    return {
        "id": f"{slug}_quiz",
        "title": _DEFAULT_QUIZ_TITLE,
        "passing_score": _DEFAULT_PASSING_SCORE,
        "version": 1,
        "randomize_questions": True,
        "randomize_options": True,
        "questions": [],
    }


class AdminQuizCreateService:
    """Create an empty ``quiz.json`` for one course and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def create_quiz(self, slug: str) -> AdminQuizCreateResult:
        """Create a new empty quiz for one course and refresh runtime."""
        course_dir = _resolve_course_dir_for_quiz_create(self._courses_dir, slug)
        quiz_json_path = course_dir / QUIZ_JSON_FILENAME

        if quiz_json_path.is_file():
            raise AdminQuizCreateError("Итоговый тест для этого курса уже создан.")

        payload = _build_initial_quiz_payload(slug)

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception("Failed to write initial quiz metadata for slug=%s", slug)
            raise AdminQuizCreateError(
                "Не удалось создать тест. Попробуйте ещё раз."
            ) from exc

        RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()

        return AdminQuizCreateResult(
            slug=slug,
            edit_url=f"/admin/courses/{slug}/quiz/edit",
        )
