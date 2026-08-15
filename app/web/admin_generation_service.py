"""Web admin orchestration for AI course generation from uploaded sources."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.ai.bootstrap import (
    create_course_with_quiz_generation_service,
    create_imported_text_generation_service,
)
from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.course_generation_wizard import (
    CourseGenerationWizard,
    Language,
    PreparedCourseGeneration,
)
from app.content.importer import CourseImporter
from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.course_with_quiz_generation_service import (
    CourseWithQuizGenerationService,
)
from app.services.imported_text_generation_service import (
    ImportedTextGenerationService,
)
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_upload_service import (
    AdminCourseFormValues,
    AdminReviewError,
    AdminUploadService,
    _web_form_to_generation_options,
)

_logger = logging.getLogger(__name__)


class AdminGenerationError(Exception):
    """Raised when admin course generation cannot proceed safely."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AdminGenerationRequest:
    """Validated input for one admin course generation attempt."""

    upload_id: str
    form_values: AdminCourseFormValues
    original_filename: str


@dataclass(frozen=True)
class AdminGenerationSuccess:
    """Result of a successful admin course generation."""

    slug: str
    title: str
    lessons_count: int
    has_quiz: bool
    course_url: str
    admin_url: str
    manage_url: str


@dataclass(frozen=True)
class AdminCourseCreatedView:
    """View model for the post-generation success page."""

    slug: str
    title: str
    lessons_count: int
    has_quiz: bool
    course_url: str
    admin_url: str
    manage_url: str


def _default_text_generation_service_factory() -> ImportedTextGenerationService:
    return create_imported_text_generation_service()


def _default_course_with_quiz_service_factory() -> CourseWithQuizGenerationService:
    return create_course_with_quiz_generation_service()


def _apply_generation_overrides(
    result: LessonGenerationResult,
    prepared: PreparedCourseGeneration,
    description_override: str,
) -> LessonGenerationResult:
    """Merge administrator overrides into AI-generated course metadata."""
    course = result.course
    base_language = (
        course.language
        if course is not None and course.language
        else prepared.output_language.value
    )
    base_title = course.title if course is not None else None
    base_description = (
        course.description if course is not None and course.description is not None else ""
    )

    title = prepared.course_title or base_title
    description = description_override.strip() or base_description
    language = prepared.output_language.value
    if language == Language.AUTO.value:
        language = base_language

    return LessonGenerationResult(
        lessons=result.lessons,
        course=GeneratedCourseMetadata(
            language=language,
            title=title,
            description=description,
        ),
    )


def _read_persisted_course_slug(course_directory: Path) -> str:
    course_json = course_directory / "course.json"
    if not course_json.is_file():
        raise AdminGenerationError(
            "Не удалось сохранить курс. Проверьте параметры и попробуйте снова."
        )
    payload = json.loads(course_json.read_text(encoding="utf-8"))
    slug = str(payload.get("slug") or course_directory.name).strip()
    if not slug:
        raise AdminGenerationError(
            "Не удалось сохранить курс. Проверьте параметры и попробуйте снова."
        )
    return slug


def _map_generation_exception(exc: Exception) -> AdminGenerationError:
    if isinstance(exc, AdminGenerationError):
        return exc
    if isinstance(exc, AdminReviewError):
        return AdminGenerationError(exc.message)
    if isinstance(exc, FileNotFoundError):
        return AdminGenerationError(
            "Загруженный файл не найден. Загрузите файл заново."
        )
    if isinstance(exc, (ValueError, IsADirectoryError)):
        return AdminGenerationError(
            "Некорректные параметры генерации. Проверьте форму и попробуйте снова."
        )
    _logger.exception("Admin course generation failed")
    return AdminGenerationError(
        "Не удалось создать курс. Проверьте исходный файл и параметры и попробуйте снова."
    )


class AdminGenerationService:
    """Orchestrate web admin course generation using the existing AI pipeline."""

    def __init__(
        self,
        upload_service: AdminUploadService,
        courses_dir: Path,
        runtime: ContentRuntime,
        *,
        importer: Optional[CourseImporter] = None,
        text_generation_service: Optional[ImportedTextGenerationService] = None,
        course_with_quiz_service: Optional[CourseWithQuizGenerationService] = None,
        text_generation_service_factory: Callable[
            [], ImportedTextGenerationService
        ] = _default_text_generation_service_factory,
        course_with_quiz_service_factory: Callable[
            [], CourseWithQuizGenerationService
        ] = _default_course_with_quiz_service_factory,
    ) -> None:
        self._upload_service = upload_service
        self._courses_dir = courses_dir
        self._runtime = runtime
        self._importer = importer if importer is not None else CourseImporter()
        self._text_generation_service = text_generation_service
        self._course_with_quiz_service = course_with_quiz_service
        self._text_generation_service_factory = text_generation_service_factory
        self._course_with_quiz_service_factory = course_with_quiz_service_factory

    def generate_course(self, request: AdminGenerationRequest) -> AdminGenerationSuccess:
        """Generate and persist a course from a stored upload and wizard options."""
        try:
            return self._generate_course(request)
        except Exception as exc:
            raise _map_generation_exception(exc) from exc

    def build_created_view(self, slug: str) -> Optional[AdminCourseCreatedView]:
        """Build the success page view for a generated course slug."""
        course = self._runtime.get_course(slug)
        if course is None:
            return None
        return AdminCourseCreatedView(
            slug=course.slug,
            title=course.title,
            lessons_count=len(course.lessons),
            has_quiz=course.quiz is not None,
            course_url=f"/courses/{course.slug}",
            admin_url="/admin",
            manage_url=f"/admin/courses/{course.slug}",
        )

    def _generate_course(self, request: AdminGenerationRequest) -> AdminGenerationSuccess:
        resolved = self._upload_service.resolve_upload(request.upload_id)
        options = _web_form_to_generation_options(
            resolved.source_path,
            request.form_values,
        )
        prepared = CourseGenerationWizard().prepare(options)

        text = self._importer.read_source(resolved.source_path)
        output_language = prepared.output_language.value
        text_generation_service = self._resolve_text_generation_service()
        lesson_result = text_generation_service.generate_from_text(
            text,
            output_language=output_language,
        )
        lesson_result = _apply_generation_overrides(
            lesson_result,
            prepared,
            request.form_values.description,
        )

        course_with_quiz_service = self._resolve_course_with_quiz_service()
        workflow_result = course_with_quiz_service.generate_and_persist(
            lesson_result,
            self._courses_dir,
            generate_quiz=prepared.generate_quiz,
            questions_per_lesson=prepared.questions_per_lesson,
            output_language=output_language,
        )

        slug = _read_persisted_course_slug(workflow_result.course_directory)
        refresh_service = RuntimeRefreshService(
            ContentRuntimeManager(self._runtime),
        )
        refresh_service.refresh()

        title = lesson_result.course.title if lesson_result.course else slug
        if not title:
            title = slug

        return AdminGenerationSuccess(
            slug=slug,
            title=title,
            lessons_count=len(lesson_result.lessons),
            has_quiz=workflow_result.quiz_path is not None,
            course_url=f"/courses/{slug}",
            admin_url="/admin",
            manage_url=f"/admin/courses/{slug}",
        )

    def _resolve_text_generation_service(self) -> ImportedTextGenerationService:
        if self._text_generation_service is not None:
            return self._text_generation_service
        return self._text_generation_service_factory()

    def _resolve_course_with_quiz_service(self) -> CourseWithQuizGenerationService:
        if self._course_with_quiz_service is not None:
            return self._course_with_quiz_service
        return self._course_with_quiz_service_factory()
