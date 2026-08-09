"""Admin dashboard data for the Web UI.

This module builds course-level admin rows from published runtime content.
No database access is performed in this step.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.content.runtime import ContentRuntime


@dataclass(frozen=True)
class AdminLanguageOption:
    """One selectable language option for the course creation form."""

    value: str
    label: str


@dataclass(frozen=True)
class AdminCourseCreateView:
    """View model for the course creation wizard foundation page."""

    language_options: tuple[AdminLanguageOption, ...]


LANGUAGE_OPTIONS: tuple[AdminLanguageOption, ...] = (
    AdminLanguageOption("auto", "Авто"),
    AdminLanguageOption("ru", "Русский"),
    AdminLanguageOption("kk", "Қазақша"),
    AdminLanguageOption("en", "English"),
)


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
                )
            )
        return tuple(items)

    def get_course_create_view(self) -> AdminCourseCreateView:
        """Return the static view model for the course creation form."""
        return AdminCourseCreateView(language_options=LANGUAGE_OPTIONS)
