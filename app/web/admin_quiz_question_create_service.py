"""Admin quiz question creation and deletion for the Web UI."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

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
    AdminQuizLessonOption,
    AdminQuizQuestionEditError,
    _validate_difficulty,
    _validate_lesson,
    _validate_question_identifier,
)

_logger = logging.getLogger(__name__)

_STANDARD_OPTION_IDS = ("a", "b", "c", "d")
_STANDARD_OPTION_COUNT = 4
_QUESTION_ID_PATTERN = re.compile(r"^q(\d+)$")


class AdminQuizQuestionCreateError(Exception):
    """Raised when admin quiz question cannot be created or deleted safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminQuizQuestionCreateView:
    slug: str
    course_title: str
    course_lessons: tuple[AdminQuizLessonOption, ...]
    quiz_edit_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminQuizQuestionCreateRequest:
    slug: str
    text: str
    option_texts: tuple[str, ...]
    correct_option_index: Union[str, int]
    explanation: str
    lesson: str
    difficulty: Union[str, int]
    tags: list[str]


@dataclass(frozen=True)
class AdminQuizQuestionCreateResult:
    slug: str
    question_id: str


@dataclass(frozen=True)
class AdminQuizQuestionDeleteRequest:
    slug: str
    question_id: str


@dataclass(frozen=True)
class AdminQuizQuestionDeleteResult:
    slug: str


def _validate_option_texts_create(raw_texts: tuple[str, ...]) -> tuple[str, ...]:
    if len(raw_texts) != _STANDARD_OPTION_COUNT:
        raise AdminQuizQuestionCreateError("Текст каждого варианта ответа обязателен.")

    validated: list[str] = []
    for raw in raw_texts:
        text = str(raw or "").strip()
        if not text:
            raise AdminQuizQuestionCreateError("Текст каждого варианта ответа обязателен.")
        validated.append(text)
    return tuple(validated)


def _validate_correct_option_index(raw_index: Union[str, int]) -> int:
    if isinstance(raw_index, bool):
        raise AdminQuizQuestionCreateError("Выберите один правильный вариант ответа.")

    if isinstance(raw_index, int):
        value = raw_index
    else:
        text = str(raw_index or "").strip()
        if not text:
            raise AdminQuizQuestionCreateError("Выберите один правильный вариант ответа.")
        try:
            value = int(text)
        except ValueError as exc:
            raise AdminQuizQuestionCreateError(
                "Выберите один правильный вариант ответа."
            ) from exc

    if value < 0 or value >= _STANDARD_OPTION_COUNT:
        raise AdminQuizQuestionCreateError("Выберите один правильный вариант ответа.")
    return value


def _next_question_id(questions: list) -> str:
    max_num = 0
    for item in questions:
        if not isinstance(item, dict):
            continue
        qid = item.get("id")
        if not isinstance(qid, str):
            continue
        match = _QUESTION_ID_PATTERN.match(qid.strip())
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"q{max_num + 1}"


def _build_new_question_payload(
    question_id: str,
    *,
    text: str,
    option_texts: tuple[str, ...],
    correct_option_index: int,
    explanation: str,
    lesson: str,
    difficulty: int,
    tags: list[str],
) -> dict:
    correct_option_id = _STANDARD_OPTION_IDS[correct_option_index]
    return {
        "id": question_id,
        "type": "single_choice",
        "text": text,
        "options": [
            {"id": option_id, "text": option_texts[index]}
            for index, option_id in enumerate(_STANDARD_OPTION_IDS)
        ],
        "correct_option_ids": [correct_option_id],
        "explanation": explanation,
        "lesson": lesson,
        "difficulty": difficulty,
        "tags": tags,
    }


class AdminQuizQuestionCreateService:
    """Create and delete quiz questions in ``quiz.json`` and refresh runtime."""

    def __init__(self, courses_dir, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_create_view(self, slug: str) -> Optional[AdminQuizQuestionCreateView]:
        """Return the create form view for one course quiz, or ``None`` if missing."""
        course = self._runtime.get_course(slug)
        if course is None or course.quiz is None:
            return None

        return self._build_create_view(course)

    def get_create_view_for_errors(self, slug: str) -> Optional[AdminQuizQuestionCreateView]:
        """Return a create view for validation errors even when runtime quiz is stale."""
        course = self._runtime.get_course(slug)
        if course is None:
            return None
        return self._build_create_view(course)

    def _build_create_view(self, course) -> AdminQuizQuestionCreateView:
        course_lessons = tuple(
            AdminQuizLessonOption(id=lesson.path.name, title=lesson.title)
            for lesson in course.lessons
        )
        return AdminQuizQuestionCreateView(
            slug=course.slug,
            course_title=course.title,
            course_lessons=course_lessons,
            quiz_edit_url=f"/admin/courses/{course.slug}/quiz/edit",
            cancel_url=f"/admin/courses/{course.slug}/quiz/edit",
        )

    def create_question(
        self,
        request: AdminQuizQuestionCreateRequest,
    ) -> AdminQuizQuestionCreateResult:
        """Validate, persist a new quiz question, and refresh runtime."""
        text = _validate_question_text_for_create(request.text)
        option_texts = _validate_option_texts_create(request.option_texts)
        correct_option_index = _validate_correct_option_index(request.correct_option_index)
        explanation = str(request.explanation or "")
        tags = list(request.tags)

        try:
            quiz_json_path = _resolve_quiz_json_path(self._courses_dir, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionCreateError(exc.message) from exc

        course = self._runtime.get_course(request.slug)
        if course is None:
            raise AdminQuizQuestionCreateError("Курс не найден.")

        valid_lesson_ids = frozenset(lesson.path.name for lesson in course.lessons)
        lesson = _convert_edit_error(
            lambda: _validate_lesson(request.lesson, valid_lesson_ids)
        )
        difficulty = _convert_edit_error(
            lambda: _validate_difficulty(request.difficulty)
        )

        try:
            payload = _load_quiz_json_payload(quiz_json_path, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionCreateError(exc.message) from exc

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            raise AdminQuizQuestionCreateError("Не удалось загрузить данные теста.")

        question_id = _next_question_id(raw_questions)
        new_question = _build_new_question_payload(
            question_id,
            text=text,
            option_texts=option_texts,
            correct_option_index=correct_option_index,
            explanation=explanation,
            lesson=lesson,
            difficulty=difficulty,
            tags=tags,
        )
        raw_questions.append(new_question)

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to write new quiz question for slug=%s",
                request.slug,
            )
            raise AdminQuizQuestionCreateError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        self._refresh_runtime(request.slug)
        return AdminQuizQuestionCreateResult(slug=request.slug, question_id=question_id)

    def delete_question(
        self,
        request: AdminQuizQuestionDeleteRequest,
    ) -> AdminQuizQuestionDeleteResult:
        """Delete one quiz question and refresh runtime."""
        question_id = _validate_question_identifier_for_mutation(request.question_id)

        try:
            quiz_json_path = _resolve_quiz_json_path(self._courses_dir, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionCreateError(exc.message) from exc

        try:
            payload = _load_quiz_json_payload(quiz_json_path, request.slug)
        except AdminQuizEditError as exc:
            raise AdminQuizQuestionCreateError(exc.message) from exc

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            raise AdminQuizQuestionCreateError("Не удалось загрузить данные теста.")

        if len(raw_questions) <= 1:
            raise AdminQuizQuestionCreateError(
                "В тесте должен остаться хотя бы один вопрос."
            )

        delete_index = None
        for index, item in enumerate(raw_questions):
            if isinstance(item, dict) and item.get("id") == question_id:
                delete_index = index
                break
        if delete_index is None:
            raise AdminQuizQuestionCreateError("Вопрос не найден.")

        del raw_questions[delete_index]

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception(
                "Failed to delete quiz question for slug=%s question=%s",
                request.slug,
                question_id,
            )
            raise AdminQuizQuestionCreateError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        self._refresh_runtime(request.slug)
        return AdminQuizQuestionDeleteResult(slug=request.slug)

    def _refresh_runtime(self, slug: str) -> None:
        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Quiz question saved but runtime refresh failed for slug=%s",
                slug,
            )
            raise AdminQuizQuestionCreateError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc


def _validate_question_text_for_create(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        raise AdminQuizQuestionCreateError("Текст вопроса обязателен.")
    return text


def _validate_question_identifier_for_mutation(raw: str) -> str:
    return _convert_edit_error(lambda: _validate_question_identifier(raw))


def _convert_edit_error(callback):
    try:
        return callback()
    except AdminQuizQuestionEditError as exc:
        raise AdminQuizQuestionCreateError(exc.message) from exc
