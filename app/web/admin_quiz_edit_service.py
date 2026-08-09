"""Admin quiz settings editing for the Web UI."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from app.content.contract import COURSE_JSON_FILENAME, QUIZ_JSON_FILENAME
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_course_edit_service import _atomic_write_json

_logger = logging.getLogger(__name__)


class AdminQuizEditError(Exception):
    """Raised when admin quiz settings cannot be edited safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminQuizOptionView:
    id: str
    text: str
    is_correct: bool


@dataclass(frozen=True)
class AdminQuizQuestionView:
    id: str
    text: str
    question_type: str
    lesson: str
    difficulty: int
    explanation: str
    tags: tuple[str, ...]
    options: tuple[AdminQuizOptionView, ...]


@dataclass(frozen=True)
class AdminQuizEditView:
    slug: str
    course_title: str
    quiz_id: str
    title: str
    passing_score: int
    randomize_questions: bool
    randomize_options: bool
    questions_count: int
    questions: tuple[AdminQuizQuestionView, ...]
    detail_url: str
    cancel_url: str


@dataclass(frozen=True)
class AdminQuizEditRequest:
    slug: str
    title: str
    passing_score: Union[str, int]
    randomize_questions: bool
    randomize_options: bool


@dataclass(frozen=True)
class AdminQuizEditResult:
    slug: str


def _resolve_quiz_json_path(courses_dir: Path, slug: str) -> Path:
    """Resolve ``quiz.json`` for ``slug`` without escaping ``courses_dir``."""
    normalized = str(slug or "").strip()
    if not normalized:
        raise AdminQuizEditError("Некорректный идентификатор курса.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminQuizEditError("Некорректный идентификатор курса.")
    if ".." in Path(normalized).parts:
        raise AdminQuizEditError("Некорректный идентификатор курса.")

    courses_root = courses_dir.resolve()
    course_dir = (courses_dir / normalized).resolve()
    if os.path.commonpath([str(course_dir), str(courses_root)]) != str(courses_root):
        raise AdminQuizEditError("Некорректный идентификатор курса.")
    if course_dir.parent != courses_root:
        raise AdminQuizEditError("Некорректный идентификатор курса.")

    course_json = course_dir / COURSE_JSON_FILENAME
    if not course_json.is_file():
        raise AdminQuizEditError("Курс не найден.")

    quiz_json = course_dir / QUIZ_JSON_FILENAME
    if not quiz_json.is_file():
        raise AdminQuizEditError("Тест не найден.")
    return quiz_json


def _load_quiz_json_payload(quiz_json_path: Path, slug: str) -> dict:
    """Load existing ``quiz.json`` metadata without exposing parser details."""
    try:
        raw = quiz_json_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.exception("Failed to read quiz metadata for slug=%s", slug)
        raise AdminQuizEditError("Не удалось загрузить данные теста.") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.exception("Failed to parse quiz metadata for slug=%s", slug)
        raise AdminQuizEditError("Не удалось загрузить данные теста.") from exc

    if not isinstance(payload, dict):
        raise AdminQuizEditError("Не удалось загрузить данные теста.")
    return payload


def _validate_title(raw_title: str) -> str:
    title = str(raw_title or "").strip()
    if not title:
        raise AdminQuizEditError("Название теста обязательно.")
    return title


def _validate_passing_score(raw_passing_score: Union[str, int]) -> int:
    if isinstance(raw_passing_score, bool):
        raise AdminQuizEditError("Проходной балл должен быть целым числом.")

    if isinstance(raw_passing_score, int):
        value = raw_passing_score
    else:
        text = str(raw_passing_score or "").strip()
        if not text:
            raise AdminQuizEditError("Проходной балл должен быть целым числом.")
        try:
            value = int(text)
        except ValueError as exc:
            raise AdminQuizEditError(
                "Проходной балл должен быть целым числом."
            ) from exc

    if value < 1 or value > 100:
        raise AdminQuizEditError("Проходной балл должен быть от 1 до 100.")
    return value


def _build_question_views(quiz) -> tuple[AdminQuizQuestionView, ...]:
    questions: list[AdminQuizQuestionView] = []
    for question in quiz.questions:
        correct_ids = set(question.correct_option_ids)
        options = tuple(
            AdminQuizOptionView(
                id=option.id,
                text=option.text,
                is_correct=option.id in correct_ids,
            )
            for option in question.options
        )
        questions.append(
            AdminQuizQuestionView(
                id=question.id,
                text=question.text,
                question_type=question.question_type,
                lesson=question.lesson,
                difficulty=question.difficulty,
                explanation=question.explanation,
                tags=tuple(question.tags),
                options=options,
            )
        )
    return tuple(questions)


class AdminQuizEditService:
    """Update quiz settings in ``quiz.json`` and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_edit_view(self, slug: str) -> Optional[AdminQuizEditView]:
        """Return the edit form view for one course quiz, or ``None`` if missing."""
        course = self._runtime.get_course(slug)
        if course is None or course.quiz is None:
            return None

        quiz = course.quiz
        return AdminQuizEditView(
            slug=course.slug,
            course_title=course.title,
            quiz_id=quiz.id,
            title=quiz.title,
            passing_score=quiz.passing_score,
            randomize_questions=quiz.randomize_questions,
            randomize_options=quiz.randomize_options,
            questions_count=len(quiz.questions),
            questions=_build_question_views(quiz),
            detail_url=f"/admin/courses/{course.slug}",
            cancel_url=f"/admin/courses/{course.slug}",
        )

    def update_quiz(self, request: AdminQuizEditRequest) -> AdminQuizEditResult:
        """Validate, persist, and refresh one course quiz's settings."""
        title = _validate_title(request.title)
        passing_score = _validate_passing_score(request.passing_score)

        quiz_json_path = _resolve_quiz_json_path(self._courses_dir, request.slug)
        payload = _load_quiz_json_payload(quiz_json_path, request.slug)

        payload["title"] = title
        payload["passing_score"] = passing_score
        payload["randomize_questions"] = request.randomize_questions
        payload["randomize_options"] = request.randomize_options

        try:
            _atomic_write_json(quiz_json_path, payload)
        except OSError as exc:
            _logger.exception("Failed to write quiz metadata for slug=%s", request.slug)
            raise AdminQuizEditError(
                "Не удалось сохранить изменения. Попробуйте ещё раз."
            ) from exc

        try:
            RuntimeRefreshService(ContentRuntimeManager(self._runtime)).refresh()
        except Exception as exc:
            _logger.exception(
                "Quiz saved but runtime refresh failed for slug=%s",
                request.slug,
            )
            raise AdminQuizEditError(
                "Изменения сохранены, но не удалось обновить каталог курсов. "
                "Обновите страницу или попробуйте снова."
            ) from exc

        return AdminQuizEditResult(slug=request.slug)
