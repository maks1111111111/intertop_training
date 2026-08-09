"""Admin quiz question reordering for the Web UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json
from app.web.admin_quiz_edit_service import (
    AdminQuizEditError,
    _load_quiz_json_payload,
    _resolve_quiz_json_path,
)
from app.web.admin_quiz_question_edit_service import (
    AdminQuizQuestionEditError,
    _validate_question_identifier,
)

_logger = logging.getLogger(__name__)


class AdminQuizQuestionReorderError(Exception):
    """Raised when admin quiz question order cannot be changed safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminQuizQuestionReorderRequest:
    slug: str
    question_id: str


@dataclass(frozen=True)
class AdminQuizQuestionReorderResult:
    slug: str
    changed: bool


def _validate_question_identifier_for_reorder(raw: str) -> str:
    try:
        return _validate_question_identifier(raw)
    except AdminQuizQuestionEditError as exc:
        raise AdminQuizQuestionReorderError(exc.message) from exc


class AdminQuizQuestionReorderService:
    """Reorder quiz questions in ``quiz.json`` and refresh runtime."""

    def __init__(self, courses_dir, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def move_up(
        self,
        request: AdminQuizQuestionReorderRequest,
    ) -> AdminQuizQuestionReorderResult:
        """Move one quiz question up in the questions array."""
        return self._move_question(request, offset=-1)

    def move_down(
        self,
        request: AdminQuizQuestionReorderRequest,
    ) -> AdminQuizQuestionReorderResult:
        """Move one quiz question down in the questions array."""
        return self._move_question(request, offset=1)

    def _move_question(
        self,
        request: AdminQuizQuestionReorderRequest,
        *,
        offset: int,
    ) -> AdminQuizQuestionReorderResult:
        question_id = _validate_question_identifier_for_reorder(request.question_id)

        try:
            quiz_json_path = _resolve_quiz_json_path(self._courses_dir, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionReorderError(exc.message) from exc

        try:
            payload = _load_quiz_json_payload(quiz_json_path, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionReorderError(exc.message) from exc

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            raise AdminQuizQuestionReorderError("Не удалось загрузить данные теста.")

        current_index = None
        for index, item in enumerate(raw_questions):
            if isinstance(item, dict) and item.get("id") == question_id:
                current_index = index
                break
        if current_index is None:
            raise AdminQuizQuestionReorderError("Вопрос не найден.")

        target_index = current_index + offset
        if target_index < 0 or target_index >= len(raw_questions):
            return AdminQuizQuestionReorderResult(slug=request.slug, changed=False)

        raw_questions[current_index], raw_questions[target_index] = (
            raw_questions[target_index],
            raw_questions[current_index],
        )

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to reorder quiz question for slug=%s question=%s",
                request.slug,
                question_id,
            )
            raise AdminQuizQuestionReorderError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        self._refresh_runtime(request.slug)
        return AdminQuizQuestionReorderResult(slug=request.slug, changed=True)

    def _refresh_runtime(self, slug: str) -> None:
        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Quiz question reordered but runtime refresh failed for slug=%s",
                slug,
            )
            raise AdminQuizQuestionReorderError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc
