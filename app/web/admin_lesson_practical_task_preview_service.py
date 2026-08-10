"""Admin AI preview generation for practical tasks from a single lesson."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from app.ai.bootstrap import create_practical_task_generation_service
from app.ai.practical_task_generation_interfaces import PracticalTaskGenerationRequest
from app.ai.practical_task_generation_service import PracticalTaskGenerationService
from app.content.lesson_builder import LessonCandidate
from app.content.practical_task import PracticalTask
from app.content.runtime import ContentRuntime
from app.content.runtime_loader import Lesson
from app.web.admin_lesson_practical_task_preview_store import (
    AdminLessonPracticalTaskPreviewStore,
    StoredPreviewPracticalTask,
)

_logger = logging.getLogger(__name__)

_GENERATION_ERROR_MESSAGE = "Не удалось сгенерировать практическое задание."


class AdminLessonPracticalTaskPreviewError(Exception):
    """Raised when lesson practical-task preview cannot be generated safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminLessonPracticalTaskPreviewView:
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
    title: str
    description: str
    expected_result: str
    estimated_minutes: Optional[int]
    estimated_minutes_input: str
    generated: bool


def _validate_identifier(raw: str, *, not_found_message: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise AdminLessonPracticalTaskPreviewError(not_found_message)
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise AdminLessonPracticalTaskPreviewError(not_found_message)
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


def _task_to_stored(task: PracticalTask) -> StoredPreviewPracticalTask:
    return StoredPreviewPracticalTask(
        title=task.title,
        description=task.description,
        expected_result=task.expected_result,
        estimated_minutes=task.estimated_minutes,
    )


class AdminLessonPracticalTaskPreviewService:
    """Generate read-only AI practical-task previews for one lesson."""

    def __init__(
        self,
        runtime: ContentRuntime,
        *,
        preview_store: Optional[AdminLessonPracticalTaskPreviewStore] = None,
        generation_service: Optional[PracticalTaskGenerationService] = None,
        generation_service_factory: Callable[
            [], PracticalTaskGenerationService
        ] = create_practical_task_generation_service,
    ) -> None:
        self._runtime = runtime
        self._preview_store = preview_store
        self._generation_service = generation_service
        self._generation_service_factory = generation_service_factory

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
        except AdminLessonPracticalTaskPreviewError:
            return "course"

        course = self._runtime.get_course(normalized_slug)
        if course is None:
            return "course"

        try:
            normalized_lesson_id = _validate_identifier(
                lesson_id,
                not_found_message="Некорректный идентификатор урока.",
            )
        except AdminLessonPracticalTaskPreviewError:
            return "lesson"

        if _find_lesson(course.lessons, normalized_lesson_id) is None:
            return "lesson"

        return None

    def get_preview_page(
        self,
        slug: str,
        lesson_id: str,
    ) -> Optional[AdminLessonPracticalTaskPreviewView]:
        """Return the preview page view before generation, or ``None`` if missing."""
        context = self._resolve_lesson_context(slug, lesson_id)
        if context is None:
            return None

        course, lesson = context
        return self._build_view(
            course.slug,
            lesson,
            generated=False,
            preview_id="",
            task=None,
        )

    def generate_preview(
        self,
        slug: str,
        lesson_id: str,
    ) -> AdminLessonPracticalTaskPreviewView:
        """Generate an AI practical task for preview without persisting anything."""
        context = self._resolve_lesson_context(slug, lesson_id)
        if context is None:
            raise AdminLessonPracticalTaskPreviewError("Урок не найден.")

        course, lesson = context
        try:
            lesson_candidate = _lesson_to_candidate(lesson)
            generation_service = self._resolve_generation_service()
            result = generation_service.generate_practical_task(
                PracticalTaskGenerationRequest(lesson=lesson_candidate)
            )
            stored_task = _task_to_stored(result.task)
            preview_id = self._store_generated_preview(
                course.slug,
                lesson.path.name,
                stored_task,
            )
        except AdminLessonPracticalTaskPreviewError:
            raise
        except Exception as exc:
            _logger.exception(
                "Failed to generate lesson practical-task preview slug=%s lesson_id=%s",
                slug,
                lesson_id,
            )
            raise AdminLessonPracticalTaskPreviewError(
                _GENERATION_ERROR_MESSAGE
            ) from exc

        return self._build_view(
            course.slug,
            lesson,
            generated=True,
            preview_id=preview_id,
            task=stored_task,
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
        except AdminLessonPracticalTaskPreviewError:
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
    ) -> Optional[AdminLessonPracticalTaskPreviewView]:
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
        return self._build_view(
            slug,
            lesson,
            generated=True,
            preview_id=record.preview_id,
            task=record.task,
        )

    def get_generated_preview_page_by_id(
        self,
        preview_id: str,
    ) -> Optional[AdminLessonPracticalTaskPreviewView]:
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

    def with_edited_values(
        self,
        view: AdminLessonPracticalTaskPreviewView,
        *,
        title: str,
        description: str,
        expected_result: str,
        estimated_minutes: str,
    ) -> AdminLessonPracticalTaskPreviewView:
        """Return a generated preview view with admin-edited form values preserved."""
        minutes_input = str(estimated_minutes or "")
        parsed_minutes: Optional[int] = None
        stripped = minutes_input.strip()
        if stripped:
            try:
                parsed = int(stripped)
                if parsed > 0:
                    parsed_minutes = parsed
            except ValueError:
                parsed_minutes = view.estimated_minutes

        return AdminLessonPracticalTaskPreviewView(
            slug=view.slug,
            lesson_id=view.lesson_id,
            course_title=view.course_title,
            lesson_title=view.lesson_title,
            lesson_order=view.lesson_order,
            edit_url=view.edit_url,
            cancel_url=view.cancel_url,
            generate_url=view.generate_url,
            apply_url=view.apply_url,
            preview_id=view.preview_id,
            title=title,
            description=description,
            expected_result=expected_result,
            estimated_minutes=parsed_minutes,
            estimated_minutes_input=minutes_input,
            generated=view.generated,
        )

    def _store_generated_preview(
        self,
        slug: str,
        lesson_id: str,
        task: StoredPreviewPracticalTask,
    ) -> str:
        if self._preview_store is None:
            raise AdminLessonPracticalTaskPreviewError(_GENERATION_ERROR_MESSAGE)

        return self._preview_store.save(slug, lesson_id, task)

    def _build_view(
        self,
        slug: str,
        lesson: Lesson,
        *,
        generated: bool,
        preview_id: str,
        task: Optional[StoredPreviewPracticalTask],
    ) -> AdminLessonPracticalTaskPreviewView:
        course = self._runtime.get_course(slug)
        course_title = course.title if course is not None else slug
        lesson_id = lesson.path.name
        estimated_minutes = task.estimated_minutes if task is not None else None
        estimated_minutes_input = (
            str(estimated_minutes) if estimated_minutes is not None else ""
        )
        return AdminLessonPracticalTaskPreviewView(
            slug=slug,
            lesson_id=lesson_id,
            course_title=course_title,
            lesson_title=lesson.title,
            lesson_order=lesson.number,
            edit_url=f"/admin/courses/{slug}/lessons/{lesson_id}/edit",
            cancel_url=f"/admin/courses/{slug}",
            generate_url=(
                f"/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task"
            ),
            apply_url=(
                f"/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task/apply"
            ),
            preview_id=preview_id,
            title=task.title if task is not None else "",
            description=task.description if task is not None else "",
            expected_result=task.expected_result if task is not None else "",
            estimated_minutes=estimated_minutes,
            estimated_minutes_input=estimated_minutes_input,
            generated=generated,
        )

    def _resolve_generation_service(self) -> PracticalTaskGenerationService:
        if self._generation_service is not None:
            return self._generation_service
        return self._generation_service_factory()
