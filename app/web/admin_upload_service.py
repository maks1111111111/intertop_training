"""Safe source file upload handling for the admin course creation wizard."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from app.content.course_generation_wizard import SUPPORTED_SOURCE_EXTENSIONS
from app.web.admin_service import (
    DIFFICULTY_OPTIONS,
    LESSON_SIZE_OPTIONS,
    OUTPUT_LANGUAGE_OPTIONS,
    SOURCE_LANGUAGE_OPTIONS,
    AdminSelectOption,
)


class AdminUploadError(Exception):
    """Raised when an uploaded source file fails validation."""

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
class AdminUploadConfirmView:
    """View model for the upload confirmation step."""

    original_filename: str
    file_extension: str
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
        original_filename=saved.original_filename,
        file_extension=_extension_label(saved.extension),
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
