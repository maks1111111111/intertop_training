"""Admin quiz question editing for the Web UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Union

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json
from app.web.admin_lesson_edit_service import _parse_multiline_list
from app.web.admin_quiz_edit_service import (
    AdminQuizEditError,
    _load_quiz_json_payload,
    _resolve_quiz_json_path,
)

_logger = logging.getLogger(__name__)


class AdminQuizQuestionEditError(Exception):
    """Raised when admin quiz question content cannot be edited safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminQuizQuestionOptionView:
    id: str
    text: str
    is_correct: bool


@dataclass(frozen=True)
class AdminQuizLessonOption:
    id: str
    title: str


@dataclass(frozen=True)
class AdminQuizQuestionEditView:
    slug: str
    course_title: str
    question_id: str
    text: str
    explanation: str
    lesson: str
    difficulty: int
    tags_text: str
    options: tuple[AdminQuizQuestionOptionView, ...]
    course_lessons: tuple[AdminQuizLessonOption, ...]
    quiz_edit_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminQuizQuestionEditRequest:
    slug: str
    question_id: str
    text: str
    option_texts: tuple[str, ...]
    correct_option_id: str
    explanation: str
    lesson: str
    difficulty: Union[str, int]
    tags: list[str]


@dataclass(frozen=True)
class AdminQuizQuestionEditResult:
    slug: str
    question_id: str


def _validate_question_identifier(raw: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise AdminQuizQuestionEditError("Некорректный идентификатор вопроса.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminQuizQuestionEditError("Некорректный идентификатор вопроса.")
    return normalized


def _validate_question_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        raise AdminQuizQuestionEditError("Текст вопроса обязателен.")
    return text


def _validate_option_texts(
    raw_texts: tuple[str, ...],
    expected_count: int,
) -> tuple[str, ...]:
    if len(raw_texts) != expected_count:
        raise AdminQuizQuestionEditError("Текст каждого варианта ответа обязателен.")

    validated: list[str] = []
    for raw in raw_texts:
        text = str(raw or "").strip()
        if not text:
            raise AdminQuizQuestionEditError("Текст каждого варианта ответа обязателен.")
        validated.append(text)
    return tuple(validated)


def _validate_correct_option_id(
    raw_correct: str,
    valid_option_ids: tuple[str, ...],
) -> str:
    correct = str(raw_correct or "").strip()
    if not correct or correct not in valid_option_ids:
        raise AdminQuizQuestionEditError("Выберите один правильный вариант ответа.")
    return correct


def _validate_lesson(raw_lesson: str, valid_lesson_ids: frozenset[str]) -> str:
    lesson = str(raw_lesson or "").strip()
    if lesson and lesson not in valid_lesson_ids:
        raise AdminQuizQuestionEditError("Выберите урок из текущего курса.")
    return lesson


def _validate_difficulty(raw_difficulty: Union[str, int]) -> int:
    if isinstance(raw_difficulty, bool):
        raise AdminQuizQuestionEditError(
            "Сложность должна быть целым числом от 0 до 5."
        )

    if isinstance(raw_difficulty, int):
        value = raw_difficulty
    else:
        text = str(raw_difficulty or "").strip()
        if not text:
            raise AdminQuizQuestionEditError(
                "Сложность должна быть целым числом от 0 до 5."
            )
        try:
            value = int(text)
        except ValueError as exc:
            raise AdminQuizQuestionEditError(
                "Сложность должна быть целым числом от 0 до 5."
            ) from exc

    if value < 0 or value > 5:
        raise AdminQuizQuestionEditError(
            "Сложность должна быть целым числом от 0 до 5."
        )
    return value


def _tags_to_text(tags: tuple[str, ...]) -> str:
    return "\n".join(tags)


def _find_question_payload(questions: list, question_id: str) -> Optional[dict]:
    for item in questions:
        if isinstance(item, dict) and item.get("id") == question_id:
            return item
    return None


def _extract_option_ids(question_payload: dict) -> tuple[str, ...]:
    raw_options = question_payload.get("options")
    if not isinstance(raw_options, list):
        raise AdminQuizQuestionEditError("Не удалось загрузить данные теста.")

    option_ids: list[str] = []
    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            raise AdminQuizQuestionEditError("Не удалось загрузить данные теста.")
        option_id = raw_option.get("id")
        if not isinstance(option_id, str) or not option_id.strip():
            raise AdminQuizQuestionEditError("Не удалось загрузить данные теста.")
        option_ids.append(option_id.strip())
    return tuple(option_ids)


def _apply_question_updates(
    question_payload: dict,
    *,
    text: str,
    option_texts: tuple[str, ...],
    correct_option_id: str,
    explanation: str,
    lesson: str,
    difficulty: int,
    tags: list[str],
) -> None:
    raw_options = question_payload.get("options")
    if not isinstance(raw_options, list):
        raise AdminQuizQuestionEditError("Не удалось загрузить данные теста.")
    if len(raw_options) != len(option_texts):
        raise AdminQuizQuestionEditError("Текст каждого варианта ответа обязателен.")

    for index, raw_option in enumerate(raw_options):
        if not isinstance(raw_option, dict):
            raise AdminQuizQuestionEditError("Не удалось загрузить данные теста.")
        raw_option["text"] = option_texts[index]

    question_payload["text"] = text
    question_payload["correct_option_ids"] = [correct_option_id]
    question_payload["explanation"] = explanation
    question_payload["lesson"] = lesson
    question_payload["difficulty"] = difficulty
    question_payload["tags"] = tags


class AdminQuizQuestionEditService:
    """Update one quiz question in ``quiz.json`` and refresh runtime."""

    def __init__(self, courses_dir, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_edit_view(
        self,
        slug: str,
        question_id: str,
    ) -> Optional[AdminQuizQuestionEditView]:
        """Return the edit form view for one quiz question, or ``None`` if missing."""
        course = self._runtime.get_course(slug)
        if course is None or course.quiz is None:
            return None

        normalized_question_id = str(question_id or "").strip()
        if not normalized_question_id:
            return None

        question = None
        for item in course.quiz.questions:
            if item.id == normalized_question_id:
                question = item
                break
        if question is None:
            return None

        correct_ids = set(question.correct_option_ids)
        options = tuple(
            AdminQuizQuestionOptionView(
                id=option.id,
                text=option.text,
                is_correct=option.id in correct_ids,
            )
            for option in question.options
        )
        course_lessons = tuple(
            AdminQuizLessonOption(id=lesson.path.name, title=lesson.title)
            for lesson in course.lessons
        )

        return AdminQuizQuestionEditView(
            slug=course.slug,
            course_title=course.title,
            question_id=question.id,
            text=question.text,
            explanation=question.explanation,
            lesson=question.lesson,
            difficulty=question.difficulty,
            tags_text=_tags_to_text(tuple(question.tags)),
            options=options,
            course_lessons=course_lessons,
            quiz_edit_url=f"/admin/courses/{course.slug}/quiz/edit",
            cancel_url=f"/admin/courses/{course.slug}/quiz/edit",
        )

    def update_question(
        self,
        request: AdminQuizQuestionEditRequest,
    ) -> AdminQuizQuestionEditResult:
        """Validate, persist, and refresh one quiz question."""
        question_id = _validate_question_identifier(request.question_id)
        text = _validate_question_text(request.text)
        explanation = str(request.explanation or "")
        tags = list(request.tags)

        try:
            quiz_json_path = _resolve_quiz_json_path(self._courses_dir, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionEditError(exc.message) from exc

        course = self._runtime.get_course(request.slug)
        if course is None:
            raise AdminQuizQuestionEditError("Курс не найден.")

        valid_lesson_ids = frozenset(lesson.path.name for lesson in course.lessons)
        lesson = _validate_lesson(request.lesson, valid_lesson_ids)
        difficulty = _validate_difficulty(request.difficulty)

        try:
            payload = _load_quiz_json_payload(quiz_json_path, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionEditError(exc.message) from exc
        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            raise AdminQuizQuestionEditError("Не удалось загрузить данные теста.")

        question_payload = _find_question_payload(raw_questions, question_id)
        if question_payload is None:
            raise AdminQuizQuestionEditError("Вопрос не найден.")

        option_ids = _extract_option_ids(question_payload)
        option_texts = _validate_option_texts(request.option_texts, len(option_ids))
        correct_option_id = _validate_correct_option_id(
            request.correct_option_id,
            option_ids,
        )

        _apply_question_updates(
            question_payload,
            text=text,
            option_texts=option_texts,
            correct_option_id=correct_option_id,
            explanation=explanation,
            lesson=lesson,
            difficulty=difficulty,
            tags=tags,
        )

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to write quiz question for slug=%s question=%s",
                request.slug,
                question_id,
            )
            raise AdminQuizQuestionEditError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Quiz question saved but runtime refresh failed for slug=%s",
                request.slug,
            )
            raise AdminQuizQuestionEditError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc

        return AdminQuizQuestionEditResult(slug=request.slug, question_id=question_id)


def parse_question_tags(raw: str) -> list[str]:
    """Parse admin quiz question tags from one-tag-per-line input."""
    return _parse_multiline_list(raw)
