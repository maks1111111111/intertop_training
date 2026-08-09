"""Apply selected AI-generated lesson question previews to course quiz."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json
from app.web.admin_lesson_question_preview_store import (
    AdminLessonQuestionPreviewStore,
    AdminLessonQuestionPreviewStoreError,
    StoredPreviewQuestion,
    _validate_preview_id,
)
from app.web.admin_quiz_edit_service import (
    AdminQuizEditError,
    _load_quiz_json_payload,
    _resolve_quiz_json_path,
)
from app.web.admin_quiz_question_create_service import _next_question_id

_logger = logging.getLogger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class AdminLessonQuestionApplyError(Exception):
    """Raised when selected preview questions cannot be applied safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminLessonQuestionApplyRequest:
    slug: str
    lesson_id: str
    preview_id: str
    selected_indexes: tuple[int, ...]


@dataclass(frozen=True)
class AdminLessonQuestionApplyResult:
    slug: str
    added_question_ids: tuple[str, ...]


def _validate_identifier(raw: str, *, not_found_message: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise AdminLessonQuestionApplyError(not_found_message)
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminLessonQuestionApplyError(not_found_message)
    if not _IDENTIFIER_PATTERN.match(normalized):
        raise AdminLessonQuestionApplyError(not_found_message)
    return normalized


def _parse_selected_indexes(raw_values: list) -> tuple[int, ...]:
    if not raw_values:
        raise AdminLessonQuestionApplyError("Выберите хотя бы один вопрос.")

    indexes: list[int] = []
    seen: set[int] = set()
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            index = int(text)
        except ValueError as exc:
            raise AdminLessonQuestionApplyError(
                "Выберите хотя бы один вопрос."
            ) from exc
        if index < 0 or index in seen:
            raise AdminLessonQuestionApplyError("Выберите хотя бы один вопрос.")
        seen.add(index)
        indexes.append(index)

    if not indexes:
        raise AdminLessonQuestionApplyError("Выберите хотя бы один вопрос.")
    return tuple(indexes)


def _validate_preview_question(question: StoredPreviewQuestion) -> None:
    text = str(question.text or "").strip()
    if not text:
        raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")

    if len(question.options) < 2:
        raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")

    option_ids: set[str] = set()
    for option_id, option_text in question.options:
        normalized_id = str(option_id or "").strip()
        normalized_text = str(option_text or "").strip()
        if not normalized_id or not normalized_text:
            raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")
        if normalized_id in option_ids:
            raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")
        option_ids.add(normalized_id)

    correct_ids = tuple(
        str(item).strip()
        for item in question.correct_option_ids
        if str(item or "").strip()
    )
    if len(correct_ids) != 1:
        raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")
    if correct_ids[0] not in option_ids:
        raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")

    if question.question_type != "single_choice":
        raise AdminLessonQuestionApplyError("Не удалось добавить выбранные вопросы.")


def _build_question_payload(
    question_id: str,
    question: StoredPreviewQuestion,
    lesson_id: str,
) -> dict:
    return {
        "id": question_id,
        "type": question.question_type,
        "text": str(question.text).strip(),
        "options": [
            {"id": option_id, "text": str(option_text).strip()}
            for option_id, option_text in question.options
        ],
        "correct_option_ids": [question.correct_option_ids[0]],
        "explanation": question.explanation,
        "lesson": lesson_id,
        "difficulty": question.difficulty,
        "tags": list(question.tags),
        **({"ai_context": question.ai_context} if question.ai_context else {}),
    }


class AdminLessonQuestionApplyService:
    """Append selected AI preview questions to an existing course quiz."""

    def __init__(
        self,
        courses_dir,
        runtime: ContentRuntime,
        preview_store: AdminLessonQuestionPreviewStore,
    ) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime
        self._preview_store = preview_store

    def apply_selected_questions(
        self,
        request: AdminLessonQuestionApplyRequest,
    ) -> AdminLessonQuestionApplyResult:
        """Validate preview state and append selected questions to ``quiz.json``."""
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
        except AdminLessonQuestionPreviewStoreError as exc:
            raise AdminLessonQuestionApplyError(exc.message) from exc

        record = self._preview_store.get(preview_id)
        if record is None:
            raise AdminLessonQuestionApplyError(
                "Предпросмотр вопросов недоступен. Сгенерируйте вопросы снова."
            )
        if record.slug != slug or record.lesson_id != lesson_id:
            raise AdminLessonQuestionApplyError(
                "Предпросмотр вопросов недоступен. Сгенерируйте вопросы снова."
            )

        selected_indexes = request.selected_indexes
        for index in selected_indexes:
            if index >= len(record.questions):
                raise AdminLessonQuestionApplyError("Выберите хотя бы один вопрос.")

        selected_questions = tuple(record.questions[index] for index in selected_indexes)
        for question in selected_questions:
            _validate_preview_question(question)

        try:
            quiz_json_path = _resolve_quiz_json_path(self._courses_dir, slug)
        except AdminQuizEditError as exc:
            if exc.message == "Тест не найден.":
                raise AdminLessonQuestionApplyError(
                    "Итоговый тест для курса не найден."
                ) from exc
            raise AdminLessonQuestionApplyError(exc.message) from exc

        try:
            payload = _load_quiz_json_payload(quiz_json_path, slug)
        except AdminQuizEditError as exc:
            raise AdminLessonQuestionApplyError(exc.message) from exc

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            raise AdminLessonQuestionApplyError("Не удалось загрузить данные теста.")

        next_id_num = _extract_next_question_number(raw_questions)
        added_ids: list[str] = []
        for offset, question in enumerate(selected_questions):
            question_id = f"q{next_id_num + offset}"
            added_ids.append(question_id)
            raw_questions.append(
                _build_question_payload(question_id, question, lesson_id)
            )

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to apply lesson preview questions for slug=%s lesson=%s",
                slug,
                lesson_id,
            )
            raise AdminLessonQuestionApplyError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        self._preview_store.consume(preview_id)
        self._refresh_runtime(slug)
        return AdminLessonQuestionApplyResult(
            slug=slug,
            added_question_ids=tuple(added_ids),
        )

    def _refresh_runtime(self, slug: str) -> None:
        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Applied preview questions but runtime refresh failed for slug=%s",
                slug,
            )
            raise AdminLessonQuestionApplyError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc


def _extract_next_question_number(raw_questions: list) -> int:
    next_id = _next_question_id(raw_questions)
    match = re.match(r"^q(\d+)$", next_id)
    if not match:
        return 1
    return int(match.group(1))


def parse_selected_question_indexes(form_values: list) -> tuple[int, ...]:
    """Parse selected preview question indexes from submitted form values."""
    return _parse_selected_indexes(form_values)
