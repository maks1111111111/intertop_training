"""Safe source file upload handling for the admin course creation wizard."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from app.content.course_generation_wizard import (
    CourseGenerationOptions,
    CourseGenerationWizard,
    DifficultyLevel,
    Language,
    LessonSize,
    SUPPORTED_SOURCE_EXTENSIONS,
)
from app.web.admin_service import (
    DIFFICULTY_OPTIONS,
    LESSON_SIZE_OPTIONS,
    OUTPUT_LANGUAGE_OPTIONS,
    SOURCE_LANGUAGE_OPTIONS,
    AdminSelectOption,
)


_UPLOAD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
# Web generation uses adaptive quiz sizing (questions_per_lesson=0) when quiz
# is enabled. Actual per-lesson counts are computed by quiz_coverage policy.
_ADAPTIVE_QUESTIONS_PER_LESSON = 0


class AdminUploadError(Exception):
    """Raised when an uploaded source file fails validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AdminReviewError(Exception):
    """Raised when the generation review step receives invalid state."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class SavedUpload:
    """Metadata for a safely stored admin source upload."""

    upload_id: str
    original_filename: str
    stored_filename: str
    stored_path: Path
    extension: str


@dataclass(frozen=True)
class AdminCourseFormValues:
    """Submitted course creation wizard form values."""

    course_title: str
    description: str
    source_language: str
    output_language: str
    lesson_count: str
    lesson_size: str
    difficulty: str
    generate_quiz: bool
    include_practical_tasks: bool
    include_checklists: bool
    include_explanations: bool


@dataclass(frozen=True)
class ResolvedUpload:
    """Server-side reference to a stored upload resolved by upload_id."""

    upload_id: str
    source_path: Path
    extension: str


@dataclass(frozen=True)
class AdminUploadConfirmView:
    """View model for the upload confirmation step."""

    upload_id: str
    original_filename: str
    file_extension: str
    form_values: AdminCourseFormValues
    course_title: str
    description: str
    source_language_label: str
    output_language_label: str
    lesson_count: str
    lesson_size_label: str
    difficulty_label: str
    generate_quiz: bool
    include_practical_tasks: bool
    include_checklists: bool
    include_explanations: bool
    edit_url: str
    review_url: str


@dataclass(frozen=True)
class AdminGenerationReviewView:
    """View model for the pre-generation review step."""

    upload_id: str
    original_filename: str
    file_extension: str
    form_values: AdminCourseFormValues
    course_title: str
    description: str
    source_language_label: str
    output_language_label: str
    lesson_count: str
    lesson_size_label: str
    difficulty_label: str
    generate_quiz: bool
    include_practical_tasks: bool
    include_checklists: bool
    include_explanations: bool
    back_url: str
    loading_url: str
    generate_url: str
    status_message: str
    generation_note: str
    error_message: str = ""


@dataclass(frozen=True)
class AdminGenerationLoadingView:
    """View model for the AI course generation loading step."""

    upload_id: str
    original_filename: str
    form_values: AdminCourseFormValues
    generate_url: str


def _safe_filename(name: str) -> str:
    """Return a path-safe basename for display and extension detection."""
    basename = os.path.basename(name.replace("\\", "/"))
    safe = re.sub(r"[^\w.\-]", "_", basename)
    if not safe or safe in (".", ".."):
        return "upload"
    return safe


def _label_for(options: tuple[AdminSelectOption, ...], value: str) -> str:
    for option in options:
        if option.value == value:
            return option.label
    return value


def _extension_label(extension: str) -> str:
    labels = {
        ".pdf": "PDF",
        ".docx": "DOCX",
        ".pptx": "PPTX",
        ".mp4": "MP4",
    }
    return labels.get(extension.lower(), extension.upper().lstrip("."))


def parse_admin_course_form(form: Mapping[str, object]) -> AdminCourseFormValues:
    """Extract wizard form values from submitted multipart data."""
    return AdminCourseFormValues(
        course_title=str(form.get("course_title") or "").strip(),
        description=str(form.get("description") or "").strip(),
        source_language=str(form.get("source_language") or "auto"),
        output_language=str(form.get("output_language") or "ru"),
        lesson_count=str(form.get("lesson_count") or "5").strip(),
        lesson_size=str(form.get("lesson_size") or "medium"),
        difficulty=str(form.get("difficulty") or "beginner"),
        generate_quiz=form.get("generate_quiz") == "1",
        include_practical_tasks=form.get("include_practical_tasks") == "1",
        include_checklists=form.get("include_checklists") == "1",
        include_explanations=form.get("include_explanations") == "1",
    )


def build_upload_confirm_view(
    saved: SavedUpload,
    form_values: AdminCourseFormValues,
) -> AdminUploadConfirmView:
    """Build the confirmation page view from upload and form data."""
    return AdminUploadConfirmView(
        upload_id=saved.upload_id,
        original_filename=saved.original_filename,
        file_extension=_extension_label(saved.extension),
        form_values=form_values,
        course_title=form_values.course_title,
        description=form_values.description,
        source_language_label=_label_for(
            SOURCE_LANGUAGE_OPTIONS,
            form_values.source_language,
        ),
        output_language_label=_label_for(
            OUTPUT_LANGUAGE_OPTIONS,
            form_values.output_language,
        ),
        lesson_count=form_values.lesson_count,
        lesson_size_label=_label_for(
            LESSON_SIZE_OPTIONS,
            form_values.lesson_size,
        ),
        difficulty_label=_label_for(
            DIFFICULTY_OPTIONS,
            form_values.difficulty,
        ),
        generate_quiz=form_values.generate_quiz,
        include_practical_tasks=form_values.include_practical_tasks,
        include_checklists=form_values.include_checklists,
        include_explanations=form_values.include_explanations,
        edit_url="/admin/courses/new",
        review_url="/admin/courses/new/review",
    )


def _parse_lesson_count(raw_value: str) -> int:
    try:
        return int(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise AdminReviewError(
            "Некорректное количество уроков. Укажите целое число не меньше 1."
        ) from exc


def _parse_enum_value(enum_cls, raw_value: str, field_label: str):
    try:
        return enum_cls(str(raw_value).strip())
    except ValueError as exc:
        raise AdminReviewError(
            f"Некорректное значение поля «{field_label}»."
        ) from exc


def _web_form_to_generation_options(
    source_path: Path,
    form_values: AdminCourseFormValues,
) -> CourseGenerationOptions:
    """Map submitted wizard form values to generation options."""
    course_title = form_values.course_title or None
    lesson_count = _parse_lesson_count(form_values.lesson_count)
    source_language = _parse_enum_value(
        Language,
        form_values.source_language,
        "Язык исходного документа",
    )
    output_language = _parse_enum_value(
        Language,
        form_values.output_language,
        "Язык курса",
    )
    lesson_size = _parse_enum_value(
        LessonSize,
        form_values.lesson_size,
        "Размер уроков",
    )
    difficulty = _parse_enum_value(
        DifficultyLevel,
        form_values.difficulty,
        "Уровень сложности",
    )
    questions_per_lesson = (
        _ADAPTIVE_QUESTIONS_PER_LESSON
        if form_values.generate_quiz
        else 0
    )
    return CourseGenerationOptions(
        source_path=source_path,
        source_language=source_language,
        output_language=output_language,
        course_title=course_title,
        difficulty=difficulty,
        lesson_count=lesson_count,
        lesson_size=lesson_size,
        generate_quiz=form_values.generate_quiz,
        questions_per_lesson=questions_per_lesson,
        include_explanations=form_values.include_explanations,
        include_practical_tasks=form_values.include_practical_tasks,
        include_checklists=form_values.include_checklists,
    )


def _format_wizard_error(exc: ValueError) -> str:
    message = str(exc)
    if "lesson_count" in message:
        return "Некорректное количество уроков. Укажите целое число не меньше 1."
    if "course_title" in message:
        return "Некорректное название курса."
    return "Некорректные параметры генерации. Проверьте форму и попробуйте снова."


def build_generation_review_view(
    upload_service: AdminUploadService,
    upload_id: str,
    form_values: AdminCourseFormValues,
    *,
    original_filename: str,
    error_message: str = "",
) -> AdminGenerationReviewView:
    """Validate upload and wizard options, then build the review page view."""
    resolved = upload_service.resolve_upload(upload_id)
    options = _web_form_to_generation_options(resolved.source_path, form_values)
    try:
        CourseGenerationWizard().prepare(options)
    except FileNotFoundError as exc:
        raise AdminReviewError(
            "Загруженный файл не найден. Загрузите файл заново."
        ) from exc
    except (ValueError, IsADirectoryError) as exc:
        raise AdminReviewError(_format_wizard_error(exc)) from exc

    safe_filename = _safe_filename(original_filename) if original_filename else "upload"
    return AdminGenerationReviewView(
        upload_id=resolved.upload_id,
        original_filename=safe_filename,
        file_extension=_extension_label(resolved.extension),
        form_values=form_values,
        course_title=form_values.course_title,
        description=form_values.description,
        source_language_label=_label_for(
            SOURCE_LANGUAGE_OPTIONS,
            form_values.source_language,
        ),
        output_language_label=_label_for(
            OUTPUT_LANGUAGE_OPTIONS,
            form_values.output_language,
        ),
        lesson_count=form_values.lesson_count,
        lesson_size_label=_label_for(
            LESSON_SIZE_OPTIONS,
            form_values.lesson_size,
        ),
        difficulty_label=_label_for(
            DIFFICULTY_OPTIONS,
            form_values.difficulty,
        ),
        generate_quiz=form_values.generate_quiz,
        include_practical_tasks=form_values.include_practical_tasks,
        include_checklists=form_values.include_checklists,
        include_explanations=form_values.include_explanations,
        back_url="/admin/courses/new",
        loading_url="/admin/courses/new/loading",
        generate_url="/admin/courses/new/generate",
        status_message="Материал готов к созданию курса",
        generation_note=(
            "Проверьте параметры и нажмите «Создать курс» для запуска генерации."
        ),
        error_message=error_message,
    )


def build_generation_loading_view(
    upload_service: AdminUploadService,
    upload_id: str,
    form_values: AdminCourseFormValues,
    *,
    original_filename: str,
) -> AdminGenerationLoadingView:
    """Validate upload and wizard options, then build the loading page view."""
    review_view = build_generation_review_view(
        upload_service,
        upload_id,
        form_values,
        original_filename=original_filename,
    )
    return AdminGenerationLoadingView(
        upload_id=review_view.upload_id,
        original_filename=review_view.original_filename,
        form_values=review_view.form_values,
        generate_url=review_view.generate_url,
    )


class AdminUploadService:
    """Validate and persist admin course source uploads."""

    def __init__(self, upload_dir: Path) -> None:
        self._upload_dir = upload_dir

    @property
    def upload_dir(self) -> Path:
        """Return the configured upload storage directory."""
        return self._upload_dir

    def save_upload(self, filename: Optional[str], content: bytes) -> SavedUpload:
        """Validate and persist one uploaded source file.

        Args:
            filename: Original client filename.
            content: Raw uploaded bytes.

        Returns:
            Metadata for the stored upload.

        Raises:
            AdminUploadError: If validation fails.
        """
        if not filename or not str(filename).strip():
            raise AdminUploadError(
                "Файл не выбран. Загрузите документ или видео."
            )

        if not content:
            raise AdminUploadError(
                "Файл пуст. Загрузите документ или видео."
            )

        safe_name = _safe_filename(str(filename))
        extension = Path(safe_name).suffix.lower()
        if extension not in SUPPORTED_SOURCE_EXTENSIONS:
            supported = ", ".join(
                sorted(ext.upper().lstrip(".") for ext in SUPPORTED_SOURCE_EXTENSIONS)
            )
            raise AdminUploadError(
                f"Неподдерживаемый формат файла. Допустимые форматы: {supported}."
            )

        upload_id = uuid.uuid4().hex
        stored_filename = f"{upload_id}{extension}"
        self._upload_dir.mkdir(parents=True, exist_ok=True)

        stored_path = (self._upload_dir / stored_filename).resolve()
        upload_root = self._upload_dir.resolve()
        if os.path.commonpath([str(stored_path), str(upload_root)]) != str(upload_root):
            raise AdminUploadError("Недопустимое имя файла.")

        if stored_path.exists():
            raise AdminUploadError(
                "Не удалось сохранить файл. Попробуйте ещё раз."
            )

        stored_path.write_bytes(content)

        return SavedUpload(
            upload_id=upload_id,
            original_filename=safe_name,
            stored_filename=stored_filename,
            stored_path=stored_path,
            extension=extension,
        )

    def resolve_upload(self, upload_id: str) -> ResolvedUpload:
        """Resolve a stored upload by its server-generated identifier.

        Args:
            upload_id: Server-generated upload identifier from ``save_upload``.

        Returns:
            Resolved upload metadata including the validated source path.

        Raises:
            AdminReviewError: If the identifier is invalid or the file is missing.
        """
        normalized = str(upload_id or "").strip().lower()
        if not _UPLOAD_ID_PATTERN.fullmatch(normalized):
            raise AdminReviewError(
                "Недействительный идентификатор загрузки."
            )

        upload_root = self._upload_dir.resolve()
        matches: list[tuple[str, Path]] = []
        for extension in SUPPORTED_SOURCE_EXTENSIONS:
            candidate = (self._upload_dir / f"{normalized}{extension}").resolve()
            if os.path.commonpath([str(candidate), str(upload_root)]) != str(
                upload_root
            ):
                raise AdminReviewError(
                    "Недействительный идентификатор загрузки."
                )
            if candidate.is_file():
                matches.append((extension, candidate))

        if not matches:
            raise AdminReviewError(
                "Загруженный файл не найден. Загрузите файл заново."
            )

        extension, source_path = matches[0]
        return ResolvedUpload(
            upload_id=normalized,
            source_path=source_path,
            extension=extension,
        )
