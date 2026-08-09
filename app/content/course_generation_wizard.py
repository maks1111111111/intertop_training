"""Course generation wizard foundation for the Content Engine.

Provides typed generation options and validation that future CLI, Web,
REST, and admin interfaces can share before invoking the AI pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

_SUPPORTED_SOURCE_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".mp4"})
SUPPORTED_SOURCE_EXTENSIONS = _SUPPORTED_SOURCE_EXTENSIONS


class Language(str, Enum):
    """Language for source material or generated course content."""

    AUTO = "auto"
    RU = "ru"
    KK = "kk"
    EN = "en"


class DifficultyLevel(str, Enum):
    """Expected difficulty of the generated course."""

    BEGINNER = "beginner"
    BASIC = "basic"
    ADVANCED = "advanced"
    EXPERT = "expert"


class LessonSize(str, Enum):
    """Approximate size of each generated lesson."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass(frozen=True)
class CourseGenerationOptions:
    """User-selected parameters for AI course generation."""

    source_path: Path
    source_language: Language = Language.EN
    output_language: Language = Language.EN
    course_title: Optional[str] = None
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER
    lesson_count: int = 5
    lesson_size: LessonSize = LessonSize.MEDIUM
    generate_quiz: bool = False
    questions_per_lesson: int = 0
    include_explanations: bool = True
    include_practical_tasks: bool = False
    include_checklists: bool = False


@dataclass(frozen=True)
class PreparedCourseGeneration:
    """Validated generation options ready for the downstream pipeline."""

    source_path: Path
    source_language: Language
    output_language: Language
    course_title: Optional[str]
    difficulty: DifficultyLevel
    lesson_count: int
    lesson_size: LessonSize
    generate_quiz: bool
    questions_per_lesson: int
    include_explanations: bool
    include_practical_tasks: bool
    include_checklists: bool


class CourseGenerationWizard:
    """Validate and normalize course generation options."""

    def prepare(self, options: CourseGenerationOptions) -> PreparedCourseGeneration:
        """Validate options and return a pipeline-ready configuration.

        Args:
            options: Raw generation parameters from a caller interface.

        Returns:
            Normalized options that downstream pipeline stages can consume.

        Raises:
            ValueError: If any option is invalid.
            FileNotFoundError: If ``source_path`` does not exist.
            IsADirectoryError: If ``source_path`` is a directory.
        """
        source_path = _validate_source_path(options.source_path)
        course_title = _validate_course_title(options.course_title)
        lesson_count = _validate_lesson_count(options.lesson_count)
        questions_per_lesson = _validate_questions_per_lesson(
            options.generate_quiz,
            options.questions_per_lesson,
        )

        return PreparedCourseGeneration(
            source_path=source_path,
            source_language=options.source_language,
            output_language=options.output_language,
            course_title=course_title,
            difficulty=options.difficulty,
            lesson_count=lesson_count,
            lesson_size=options.lesson_size,
            generate_quiz=options.generate_quiz,
            questions_per_lesson=questions_per_lesson,
            include_explanations=options.include_explanations,
            include_practical_tasks=options.include_practical_tasks,
            include_checklists=options.include_checklists,
        )


def _validate_source_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    if path.is_dir():
        raise IsADirectoryError(f"Source path must be a regular file: {path}")

    if not path.is_file():
        raise ValueError(f"Source path must be a regular file: {path}")

    extension = path.suffix.lower()
    if extension not in _SUPPORTED_SOURCE_EXTENSIONS:
        supported = ", ".join(sorted(_SUPPORTED_SOURCE_EXTENSIONS))
        raise ValueError(
            f"Unsupported source file extension '{extension}'. "
            f"Supported extensions: {supported}."
        )

    return path.resolve()


def _validate_course_title(course_title: Optional[str]) -> Optional[str]:
    if course_title is None:
        return None

    if not isinstance(course_title, str):
        raise ValueError("Field 'course_title' must be a string.")

    stripped = course_title.strip()
    if not stripped:
        raise ValueError("Field 'course_title' must not be empty.")

    return stripped


def _validate_lesson_count(lesson_count: int) -> int:
    if isinstance(lesson_count, bool) or not isinstance(lesson_count, int):
        raise ValueError("Field 'lesson_count' must be an integer.")

    if lesson_count < 1:
        raise ValueError("Field 'lesson_count' must be at least 1.")

    return lesson_count


def _validate_questions_per_lesson(generate_quiz: bool, questions_per_lesson: int) -> int:
    if isinstance(questions_per_lesson, bool) or not isinstance(
        questions_per_lesson, int
    ):
        raise ValueError("Field 'questions_per_lesson' must be an integer.")

    if generate_quiz:
        if questions_per_lesson < 1:
            raise ValueError(
                "Field 'questions_per_lesson' must be at least 1 when "
                "generate_quiz is enabled."
            )
        return questions_per_lesson

    if questions_per_lesson != 0:
        raise ValueError(
            "Field 'questions_per_lesson' must be 0 when generate_quiz is disabled."
        )

    return 0
