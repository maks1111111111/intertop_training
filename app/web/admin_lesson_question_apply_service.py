"""Apply selected AI-generated lesson question previews to course quiz."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json
from app.web.admin_lesson_question_preview_store import (
    AdminLessonQuestionPreviewStore,
    AdminLessonQuestionPreviewStoreError,
    LessonQuestionPreviewRecord,
    StoredPreviewQuestion,
    _validate_preview_id,
)
from app.web.admin_quiz_edit_service import (
    AdminQuizEditError,
    _load_quiz_json_payload,
    _resolve_quiz_json_path,
)
from app.web.admin_lesson_question_edit_models import AdminLessonQuestionEditInput
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
    edited_questions: tuple[AdminLessonQuestionEditInput, ...]


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


def parse_question_edits_from_form(
    form: Mapping[str, object],
    record: LessonQuestionPreviewRecord,
) -> tuple[AdminLessonQuestionEditInput, ...]:
    """Parse admin-edited preview question fields from submitted form data."""
    edits: list[AdminLessonQuestionEditInput] = []
    for index, stored in enumerate(record.questions):
        prefix = f"question_{index}_"
        text = str(form.get(f"{prefix}text") or "")
        explanation = str(form.get(f"{prefix}explanation") or "")
        correct_option_id = str(form.get(f"{prefix}correct_option") or "").strip()
        option_texts: list[tuple[str, str]] = []
        for option_id, _ in stored.options:
            option_text = str(form.get(f"{prefix}option_{option_id}") or "")
            option_texts.append((option_id, option_text))
        edits.append(
            AdminLessonQuestionEditInput(
                index=index,
                text=text,
                option_texts=tuple(option_texts),
                correct_option_id=correct_option_id,
                explanation=explanation,
            )
        )
    return tuple(edits)


def _validate_edited_question_structure(
    stored: StoredPreviewQuestion,
    edit: AdminLessonQuestionEditInput,
) -> None:
    stored_option_ids = [option_id for option_id, _ in stored.options]
    edit_option_ids = [option_id for option_id, _ in edit.option_texts]
    if stored_option_ids != edit_option_ids:
        raise AdminLessonQuestionApplyError(
            "Некорректные данные вопроса. Сгенерируйте вопросы снова."
        )
    if stored.question_type != "single_choice":
        raise AdminLessonQuestionApplyError(
            "Некорректные данные вопроса. Сгенерируйте вопросы снова."
        )


def _merge_edited_question(
    stored: StoredPreviewQuestion,
    edit: AdminLessonQuestionEditInput,
) -> StoredPreviewQuestion:
    _validate_edited_question_structure(stored, edit)

    text = str(edit.text or "").strip()
    if not text:
        raise AdminLessonQuestionApplyError("Введите текст вопроса.")

    new_options: list[tuple[str, str]] = []
    stored_option_ids = {option_id for option_id, _ in stored.options}
    for option_id, option_text in edit.option_texts:
        normalized_text = str(option_text or "").strip()
        if not normalized_text:
            raise AdminLessonQuestionApplyError("Заполните все варианты ответа.")
        new_options.append((option_id, normalized_text))

    correct_option_id = str(edit.correct_option_id or "").strip()
    if not correct_option_id:
        raise AdminLessonQuestionApplyError("Выберите правильный ответ.")
    if correct_option_id not in stored_option_ids:
        raise AdminLessonQuestionApplyError("Выберите правильный ответ.")

    return StoredPreviewQuestion(
        text=text,
        question_type=stored.question_type,
        options=tuple(new_options),
        correct_option_ids=(correct_option_id,),
        explanation=str(edit.explanation or "").strip(),
        difficulty=stored.difficulty,
        tags=stored.tags,
        ai_context=stored.ai_context,
    )


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
                raise AdminLessonQuestionApplyError(
                    "Некорректные данные вопроса. Сгенерируйте вопросы снова."
                )

        if len(request.edited_questions) != len(record.questions):
            raise AdminLessonQuestionApplyError(
                "Некорректные данные вопроса. Сгенерируйте вопросы снова."
            )

        edits_by_index = {
            edit.index: edit for edit in request.edited_questions
        }
        if len(edits_by_index) != len(record.questions):
            raise AdminLessonQuestionApplyError(
                "Некорректные данные вопроса. Сгенерируйте вопросы снова."
            )
        for index in range(len(record.questions)):
            if index not in edits_by_index:
                raise AdminLessonQuestionApplyError(
                    "Некорректные данные вопроса. Сгенерируйте вопросы снова."
                )

        selected_questions: list[StoredPreviewQuestion] = []
        for index in selected_indexes:
            selected_questions.append(
                _merge_edited_question(
                    record.questions[index],
                    edits_by_index[index],
                )
            )

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


def parse_selected_question_indexes(form_values: Sequence[object]) -> tuple[int, ...]:
    """Parse selected preview question indexes from submitted form values."""
    return _parse_selected_indexes(list(form_values))
