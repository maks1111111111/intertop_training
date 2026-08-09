"""Admin AI preview generation for quiz questions from a single lesson."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.ai.bootstrap import create_quiz_generation_service
from app.ai.quiz_coverage import create_quiz_generation_request
from app.ai.quiz_interfaces import QuizGenerationResult
from app.ai.quiz_service import QuizGenerationService
from app.content.lesson_builder import LessonCandidate
from app.content.quiz_writer import QuizDraft, QuizWriter
from app.content.runtime import ContentRuntime
from app.content.runtime_loader import Lesson
from app.web.admin_lesson_question_preview_store import (
    AdminLessonQuestionPreviewStore,
    StoredPreviewQuestion,
)

_logger = logging.getLogger(__name__)

_GENERATION_ERROR_MESSAGE = "Не удалось сгенерировать вопросы."


class AdminLessonQuestionPreviewError(Exception):
    """Raised when lesson question preview cannot be generated safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminLessonQuestionPreviewOptionView:
    id: str
    text: str
    is_correct: bool


@dataclass(frozen=True)
class AdminLessonQuestionPreviewQuestionView:
    id: str
    text: str
    options: Tuple[AdminLessonQuestionPreviewOptionView, ...]
    explanation: str
    difficulty: int
    tags: Tuple[str, ...]


@dataclass(frozen=True)
class AdminLessonQuestionPreviewView:
    slug: str
    lesson_id: str
    course_title: str
    lesson_title: str
    lesson_order: int
    edit_url: str
    cancel_url: str
    generate_url: str
    apply_url: str
    preview_id: str
    questions: Tuple[AdminLessonQuestionPreviewQuestionView, ...]
    generated: bool


def _validate_identifier(raw: str, *, not_found_message: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise AdminLessonQuestionPreviewError(not_found_message)
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminLessonQuestionPreviewError(not_found_message)
    return normalized


def _find_lesson(course_lessons: list[Lesson], lesson_id: str) -> Optional[Lesson]:
    for candidate in course_lessons:
        if candidate.path.name == lesson_id:
            return candidate
    return None


def _lesson_to_candidate(lesson: Lesson) -> LessonCandidate:
    return LessonCandidate(
        title=lesson.title,
        content=lesson.description,
        practical_task=lesson.practical_task,
        checklist=lesson.checklist,
        common_mistakes=lesson.common_mistakes,
        key_takeaways=lesson.key_takeaways,
        application_tips=lesson.application_tips,
        structured_practical_task=lesson.structured_practical_task,
    )


def _build_preview_questions(
    result: QuizGenerationResult,
    course_slug: str,
) -> Tuple[AdminLessonQuestionPreviewQuestionView, ...]:
    draft = QuizWriter().write(result, course_slug)
    preview_questions: list[AdminLessonQuestionPreviewQuestionView] = []
    for question in draft.questions:
        correct_ids = set(question.correct_option_ids)
        options = tuple(
            AdminLessonQuestionPreviewOptionView(
                id=option.id,
                text=option.text,
                is_correct=option.id in correct_ids,
            )
            for option in question.options
        )
        preview_questions.append(
            AdminLessonQuestionPreviewQuestionView(
                id=question.id,
                text=question.text,
                options=options,
                explanation=question.explanation,
                difficulty=question.difficulty,
                tags=question.tags,
            )
        )
    return tuple(preview_questions)


def _draft_to_stored_questions(
    draft: QuizDraft,
) -> Tuple[StoredPreviewQuestion, ...]:
    stored: list[StoredPreviewQuestion] = []
    for question in draft.questions:
        stored.append(
            StoredPreviewQuestion(
                text=question.text,
                question_type=question.question_type,
                options=tuple(
                    (option.id, option.text) for option in question.options
                ),
                correct_option_ids=question.correct_option_ids,
                explanation=question.explanation,
                difficulty=question.difficulty,
                tags=question.tags,
                ai_context=question.ai_context,
            )
        )
    return tuple(stored)


class AdminLessonQuestionPreviewService:
    """Generate read-only AI quiz question previews for one lesson."""

    def __init__(
        self,
        runtime: ContentRuntime,
        *,
        preview_store: Optional[AdminLessonQuestionPreviewStore] = None,
        quiz_generation_service: Optional[QuizGenerationService] = None,
        quiz_generation_service_factory: Callable[
            [], QuizGenerationService
        ] = create_quiz_generation_service,
    ) -> None:
        self._runtime = runtime
        self._preview_store = preview_store
        self._quiz_generation_service = quiz_generation_service
        self._quiz_generation_service_factory = quiz_generation_service_factory

    def get_not_found_reason(
        self,
        slug: str,
        lesson_id: str,
    ) -> Optional[str]:
        """Return ``course`` or ``lesson`` when missing, otherwise ``None``."""
        try:
            normalized_slug = _validate_identifier(
                slug,
                not_found_message="Некорректный идентификатор курса.",
            )
        except AdminLessonQuestionPreviewError:
            return "course"

        course = self._runtime.get_course(normalized_slug)
        if course is None:
            return "course"

        try:
            normalized_lesson_id = _validate_identifier(
                lesson_id,
                not_found_message="Некорректный идентификатор урока.",
            )
        except AdminLessonQuestionPreviewError:
            return "lesson"

        if _find_lesson(course.lessons, normalized_lesson_id) is None:
            return "lesson"

        return None

    def get_preview_page(
        self,
        slug: str,
        lesson_id: str,
    ) -> Optional[AdminLessonQuestionPreviewView]:
        """Return the preview page view before generation, or ``None`` if missing."""
        context = self._resolve_lesson_context(slug, lesson_id)
        if context is None:
            return None

        course, lesson = context
        return self._build_view(
            course.slug,
            lesson,
            questions=(),
            generated=False,
            preview_id="",
        )

    def generate_preview(
        self,
        slug: str,
        lesson_id: str,
    ) -> AdminLessonQuestionPreviewView:
        """Generate AI quiz questions for preview without persisting anything."""
        context = self._resolve_lesson_context(slug, lesson_id)
        if context is None:
            raise AdminLessonQuestionPreviewError("Урок не найден.")

        course, lesson = context
        try:
            lesson_candidate = _lesson_to_candidate(lesson)
            quiz_request = create_quiz_generation_request((lesson_candidate,))
            quiz_service = self._resolve_quiz_generation_service()
            result = quiz_service.generate_quiz(quiz_request)
            draft = QuizWriter().write(result, course.slug)
            questions = _build_preview_questions(result, course.slug)
            preview_id = self._store_generated_preview(
                course.slug,
                lesson.path.name,
                draft,
            )
        except AdminLessonQuestionPreviewError:
            raise
        except Exception as exc:
            _logger.exception(
                "Failed to generate lesson question preview slug=%s lesson_id=%s",
                slug,
                lesson_id,
            )
            raise AdminLessonQuestionPreviewError(_GENERATION_ERROR_MESSAGE) from exc

        return self._build_view(
            course.slug,
            lesson,
            questions=questions,
            generated=True,
            preview_id=preview_id,
        )

    def _resolve_lesson_context(
        self,
        slug: str,
        lesson_id: str,
    ) -> Optional[tuple]:
        try:
            normalized_slug = _validate_identifier(
                slug,
                not_found_message="Некорректный идентификатор курса.",
            )
            normalized_lesson_id = _validate_identifier(
                lesson_id,
                not_found_message="Некорректный идентификатор урока.",
            )
        except AdminLessonQuestionPreviewError:
            return None

        course = self._runtime.get_course(normalized_slug)
        if course is None:
            return None

        lesson = _find_lesson(course.lessons, normalized_lesson_id)
        if lesson is None:
            return None

        return course, lesson

    def get_generated_preview_page(
        self,
        slug: str,
        lesson_id: str,
        preview_id: str,
    ) -> Optional[AdminLessonQuestionPreviewView]:
        """Rebuild a generated preview page from server-side preview storage."""
        if self._preview_store is None:
            return None

        context = self._resolve_lesson_context(slug, lesson_id)
        if context is None:
            return None

        record = self._preview_store.get(preview_id)
        if record is None:
            return None
        if record.slug != slug or record.lesson_id != lesson_id:
            return None

        _, lesson = context
        questions = self._stored_questions_to_view(record.questions)
        return self._build_view(
            slug,
            lesson,
            questions=questions,
            generated=True,
            preview_id=record.preview_id,
        )

    def get_generated_preview_page_by_id(
        self,
        preview_id: str,
    ) -> Optional[AdminLessonQuestionPreviewView]:
        """Rebuild a generated preview page using only the preview identifier."""
        if self._preview_store is None:
            return None

        record = self._preview_store.get(preview_id)
        if record is None:
            return None

        return self.get_generated_preview_page(
            record.slug,
            record.lesson_id,
            preview_id,
        )

    def _store_generated_preview(
        self,
        slug: str,
        lesson_id: str,
        draft: QuizDraft,
    ) -> str:
        if self._preview_store is None:
            raise AdminLessonQuestionPreviewError(_GENERATION_ERROR_MESSAGE)

        stored_questions = _draft_to_stored_questions(draft)
        return self._preview_store.save(slug, lesson_id, stored_questions)

    def _stored_questions_to_view(
        self,
        questions: Tuple[StoredPreviewQuestion, ...],
    ) -> Tuple[AdminLessonQuestionPreviewQuestionView, ...]:
        preview_questions: list[AdminLessonQuestionPreviewQuestionView] = []
        for index, question in enumerate(questions, start=1):
            correct_ids = set(question.correct_option_ids)
            options = tuple(
                AdminLessonQuestionPreviewOptionView(
                    id=option_id,
                    text=option_text,
                    is_correct=option_id in correct_ids,
                )
                for option_id, option_text in question.options
            )
            preview_questions.append(
                AdminLessonQuestionPreviewQuestionView(
                    id=f"preview-{index}",
                    text=question.text,
                    options=options,
                    explanation=question.explanation,
                    difficulty=question.difficulty,
                    tags=question.tags,
                )
            )
        return tuple(preview_questions)

    def _build_view(
        self,
        slug: str,
        lesson: Lesson,
        *,
        questions: Tuple[AdminLessonQuestionPreviewQuestionView, ...],
        generated: bool,
        preview_id: str,
    ) -> AdminLessonQuestionPreviewView:
        course = self._runtime.get_course(slug)
        course_title = course.title if course is not None else slug
        lesson_id = lesson.path.name
        return AdminLessonQuestionPreviewView(
            slug=slug,
            lesson_id=lesson_id,
            course_title=course_title,
            lesson_title=lesson.title,
            lesson_order=lesson.number,
            edit_url=f"/admin/courses/{slug}/lessons/{lesson_id}/edit",
            cancel_url=f"/admin/courses/{slug}",
            generate_url=(
                f"/admin/courses/{slug}/lessons/{lesson_id}/generate-questions"
            ),
            apply_url=(
                f"/admin/courses/{slug}/lessons/{lesson_id}/generate-questions/apply"
            ),
            preview_id=preview_id,
            questions=questions,
            generated=generated,
        )

    def _resolve_quiz_generation_service(self) -> QuizGenerationService:
        if self._quiz_generation_service is not None:
            return self._quiz_generation_service
        return self._quiz_generation_service_factory()
