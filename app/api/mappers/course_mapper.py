"""Map ContentRuntime course models to HTTP API DTOs."""

from __future__ import annotations

from app.api.dto.course import (
    CourseDetailDTO,
    CourseListDTO,
    CourseSummaryDTO,
    LessonDetailDTO,
    LessonSummaryDTO,
)
from app.content.runtime_loader import Course, Lesson


def to_summary(course: Course) -> CourseSummaryDTO:
    """Convert a runtime course to a list-item DTO."""
    return CourseSummaryDTO(
        slug=course.slug,
        title=course.title,
        description=course.description,
    )


def to_summary_list(courses: list[Course]) -> CourseListDTO:
    """Convert runtime courses to a list response DTO."""
    return CourseListDTO(items=[to_summary(course) for course in courses])


def to_lesson_summary(lesson: Lesson) -> LessonSummaryDTO:
    """Convert a runtime lesson to a summary DTO."""
    return LessonSummaryDTO(
        id=lesson.path.name,
        title=lesson.title,
        order=lesson.number,
    )


def to_detail(course: Course) -> CourseDetailDTO:
    """Convert a runtime course to a detail DTO."""
    return CourseDetailDTO(
        slug=course.slug,
        title=course.title,
        description=course.description,
        language=course.language,
        lessons=[to_lesson_summary(lesson) for lesson in course.lessons],
    )


def to_lesson_detail(lesson: Lesson) -> LessonDetailDTO:
    """Convert a runtime lesson to a full lesson DTO."""
    return LessonDetailDTO(
        id=lesson.path.name,
        title=lesson.title,
        order=lesson.number,
        content=lesson.description,
        practical_task=lesson.practical_task,
        checklist=list(lesson.checklist),
        common_mistakes=list(lesson.common_mistakes),
        key_takeaways=list(lesson.key_takeaways),
        application_tips=list(lesson.application_tips),
    )
