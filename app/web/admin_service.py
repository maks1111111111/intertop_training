"""Admin dashboard data for the Web UI.

This module builds course-level admin rows from published runtime content.
No database access is performed in this step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.content.course_generation_wizard import DifficultyLevel, Language, LessonSize
from app.content.runtime import ContentRuntime


@dataclass(frozen=True)
class AdminSelectOption:
    """One selectable option for admin course creation form controls."""

    value: str
    label: str


@dataclass(frozen=True)
class AdminCourseCreateView:
    """View model for the course creation wizard generation options page."""

    source_language_options: tuple[AdminSelectOption, ...]
    output_language_options: tuple[AdminSelectOption, ...]
    difficulty_options: tuple[AdminSelectOption, ...]
    lesson_size_options: tuple[AdminSelectOption, ...]


def _language_label(language: Language) -> str:
    labels = {
        Language.AUTO: "Авто",
        Language.RU: "Русский",
        Language.KK: "Қазақша",
        Language.EN: "English",
    }
    return labels[language]


def _difficulty_label(difficulty: DifficultyLevel) -> str:
    labels = {
        DifficultyLevel.BEGINNER: "Начальный",
        DifficultyLevel.BASIC: "Базовый",
        DifficultyLevel.ADVANCED: "Продвинутый",
        DifficultyLevel.EXPERT: "Экспертный",
    }
    return labels[difficulty]


def _lesson_size_label(lesson_size: LessonSize) -> str:
    labels = {
        LessonSize.SHORT: "Короткий",
        LessonSize.MEDIUM: "Средний",
        LessonSize.LONG: "Длинный",
    }
    return labels[lesson_size]


def _options_from_language(members: tuple[Language, ...]) -> tuple[AdminSelectOption, ...]:
    return tuple(
        AdminSelectOption(language.value, _language_label(language))
        for language in members
    )


def _options_from_difficulty(
    members: tuple[DifficultyLevel, ...],
) -> tuple[AdminSelectOption, ...]:
    return tuple(
        AdminSelectOption(difficulty.value, _difficulty_label(difficulty))
        for difficulty in members
    )


def _options_from_lesson_size(
    members: tuple[LessonSize, ...],
) -> tuple[AdminSelectOption, ...]:
    return tuple(
        AdminSelectOption(lesson_size.value, _lesson_size_label(lesson_size))
        for lesson_size in members
    )


SOURCE_LANGUAGE_OPTIONS: tuple[AdminSelectOption, ...] = _options_from_language(tuple(Language))
OUTPUT_LANGUAGE_OPTIONS: tuple[AdminSelectOption, ...] = _options_from_language(
    (Language.RU, Language.KK, Language.EN),
)
DIFFICULTY_OPTIONS: tuple[AdminSelectOption, ...] = _options_from_difficulty(
    tuple(DifficultyLevel),
)
LESSON_SIZE_OPTIONS: tuple[AdminSelectOption, ...] = _options_from_lesson_size(tuple(LessonSize))


def _status_label(status: str) -> str:
    labels = {
        "published": "Опубликован",
        "draft": "Черновик",
        "archived": "Архив",
    }
    return labels.get(status, status or "Неизвестно")


def _lesson_has_practical_task(lesson) -> bool:
    if lesson.structured_practical_task is not None:
        return True
    return bool(lesson.practical_task.strip())


@dataclass(frozen=True)
class AdminCourseItem:
    """One course row on the admin dashboard."""

    slug: str
    title: str
    description: str
    language: str
    lessons_count: int
    status: str
    view_url: str
    manage_url: str


@dataclass(frozen=True)
class AdminCourseLessonItem:
    """One lesson row on the admin course detail page."""

    id: str
    order: int
    title: str
    description: str
    has_practical_task: bool
    has_checklist: bool
    has_key_takeaways: bool
    has_application_tips: bool
    preview_url: str


@dataclass(frozen=True)
class AdminCourseQuizSummary:
    """Quiz summary for the admin course detail page."""

    exists: bool
    questions_count: int
    passing_score: int


@dataclass(frozen=True)
class AdminCourseDetailView:
    """Read-only admin overview for one published course."""

    slug: str
    title: str
    description: str
    language: str
    status: str
    status_label: str
    lessons_count: int
    lessons: tuple[AdminCourseLessonItem, ...]
    quiz: AdminCourseQuizSummary
    preview_url: str
    admin_url: str


class AdminService:
    """Assemble admin dashboard rows from runtime content."""

    def __init__(self, runtime: ContentRuntime) -> None:
        self._runtime = runtime

    def get_courses(self) -> tuple[AdminCourseItem, ...]:
        """Return admin rows for all published runtime courses."""
        items: list[AdminCourseItem] = []
        for course in self._runtime.get_courses():
            items.append(
                AdminCourseItem(
                    slug=course.slug,
                    title=course.title,
                    description=course.description,
                    language=course.language,
                    lessons_count=len(course.lessons),
                    status=course.status,
                    view_url=f"/courses/{course.slug}",
                    manage_url=f"/admin/courses/{course.slug}",
                )
            )
        return tuple(items)

    def get_course_detail(self, slug: str) -> Optional[AdminCourseDetailView]:
        """Return the admin detail view for one published course, or ``None``."""
        course = self._runtime.get_course(slug)
        if course is None:
            return None

        lessons: list[AdminCourseLessonItem] = []
        for lesson in course.lessons:
            lessons.append(
                AdminCourseLessonItem(
                    id=lesson.path.name,
                    order=lesson.number,
                    title=lesson.title,
                    description=lesson.description,
                    has_practical_task=_lesson_has_practical_task(lesson),
                    has_checklist=bool(lesson.checklist),
                    has_key_takeaways=bool(lesson.key_takeaways),
                    has_application_tips=bool(lesson.application_tips),
                    preview_url=(
                        f"/courses/{course.slug}/lessons/{lesson.path.name}"
                    ),
                )
            )

        if course.quiz is not None:
            quiz = AdminCourseQuizSummary(
                exists=True,
                questions_count=len(course.quiz.questions),
                passing_score=course.quiz.passing_score,
            )
        else:
            quiz = AdminCourseQuizSummary(
                exists=False,
                questions_count=0,
                passing_score=0,
            )

        return AdminCourseDetailView(
            slug=course.slug,
            title=course.title,
            description=course.description,
            language=course.language,
            status=course.status,
            status_label=_status_label(course.status),
            lessons_count=len(course.lessons),
            lessons=tuple(lessons),
            quiz=quiz,
            preview_url=f"/courses/{course.slug}",
            admin_url="/admin",
        )

    def get_course_create_view(self) -> AdminCourseCreateView:
        """Return the static view model for the course creation form."""
        return AdminCourseCreateView(
            source_language_options=SOURCE_LANGUAGE_OPTIONS,
            output_language_options=OUTPUT_LANGUAGE_OPTIONS,
            difficulty_options=DIFFICULTY_OPTIONS,
            lesson_size_options=LESSON_SIZE_OPTIONS,
        )
