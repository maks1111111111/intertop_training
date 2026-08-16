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


def quiz_json_exists(courses_dir: Path, slug: str) -> bool:
    """Return ``True`` when a course has a persisted ``quiz.json`` on disk."""
    try:
        _resolve_quiz_json_path(courses_dir, slug)
    except AdminQuizEditError:
        return False
    return True


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_passing_score(value: object) -> int:
    try:
        passing_score = int(value)
    except (TypeError, ValueError):
        return 80
    if passing_score < 1 or passing_score > 100:
        return 80
    return passing_score


def _build_question_views_from_payload(
    raw_questions: object,
) -> tuple[AdminQuizQuestionView, ...]:
    if not isinstance(raw_questions, list):
        return ()

    questions: list[AdminQuizQuestionView] = []
    for raw_question in raw_questions:
        if not isinstance(raw_question, dict):
            continue

        question_id = str(raw_question.get("id") or "").strip()
        question_text = str(raw_question.get("text") or "").strip()
        question_type = str(raw_question.get("type") or "single_choice").strip()
        lesson = str(raw_question.get("lesson") or "").strip()
        explanation = str(raw_question.get("explanation") or "").strip()
        try:
            difficulty = int(raw_question.get("difficulty", 0))
        except (TypeError, ValueError):
            difficulty = 0

        raw_tags = raw_question.get("tags")
        if isinstance(raw_tags, list):
            tags = tuple(str(tag).strip() for tag in raw_tags if str(tag).strip())
        else:
            tags = ()

        correct_ids = raw_question.get("correct_option_ids")
        correct_id_set = {
            str(item).strip()
            for item in correct_ids
            if isinstance(correct_ids, list) and str(item).strip()
        }

        raw_options = raw_question.get("options")
        options: list[AdminQuizOptionView] = []
        if isinstance(raw_options, list):
            for raw_option in raw_options:
                if not isinstance(raw_option, dict):
                    continue
                option_id = str(raw_option.get("id") or "").strip()
                option_text = str(raw_option.get("text") or "").strip()
                if not option_id:
                    continue
                options.append(
                    AdminQuizOptionView(
                        id=option_id,
                        text=option_text,
                        is_correct=option_id in correct_id_set,
                    )
                )

        if not question_id:
            continue

        questions.append(
            AdminQuizQuestionView(
                id=question_id,
                text=question_text,
                question_type=question_type or "single_choice",
                lesson=lesson,
                difficulty=difficulty,
                explanation=explanation,
                tags=tags,
                options=tuple(options),
            )
        )
    return tuple(questions)


def _build_edit_view_from_payload(
    course,
    payload: dict,
) -> AdminQuizEditView:
    quiz_id = str(payload.get("id") or "").strip() or f"{course.slug}_quiz"
    title = str(payload.get("title") or "").strip() or "Итоговый тест"
    passing_score = _coerce_passing_score(payload.get("passing_score"))
    randomize_questions = _coerce_bool(payload.get("randomize_questions"), True)
    randomize_options = _coerce_bool(payload.get("randomize_options"), True)
    questions = _build_question_views_from_payload(payload.get("questions"))

    return AdminQuizEditView(
        slug=course.slug,
        course_title=course.title,
        quiz_id=quiz_id,
        title=title,
        passing_score=passing_score,
        randomize_questions=randomize_questions,
        randomize_options=randomize_options,
        questions_count=len(questions),
        questions=questions,
        detail_url=f"/admin/courses/{course.slug}",
        cancel_url=f"/admin/courses/{course.slug}",
    )


class AdminQuizEditService:
    """Update quiz settings in ``quiz.json`` and refresh runtime."""

    def __init__(self, courses_dir: Path, runtime: ContentRuntime) -> None:
        self._courses_dir = courses_dir
        self._runtime = runtime

    def get_edit_view(self, slug: str) -> Optional[AdminQuizEditView]:
        """Return the edit form view for one course quiz, or ``None`` if missing."""
        course = self._runtime.get_course(slug)
        if course is None:
            return None

        try:
            quiz_json_path = _resolve_quiz_json_path(self._courses_dir, slug)
        except AdminQuizEditError:
            return None

        try:
            payload = _load_quiz_json_payload(quiz_json_path, slug)
        except AdminQuizEditError:
            return None

        return _build_edit_view_from_payload(course, payload)

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
