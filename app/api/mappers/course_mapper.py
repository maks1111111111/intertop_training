"""Map ContentRuntime course models to HTTP API DTOs."""

from __future__ import annotations

from app.api.dto.course import (
    CourseDetailDTO,
    CourseListDTO,
    CourseSummaryDTO,
    LessonDetailDTO,
    LessonSummaryDTO,
)
from typing import Optional

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


def _lesson_navigation(
    course: Course,
    lesson: Lesson,
) -> tuple[Optional[str], Optional[str], bool, bool]:
    """Return previous/next lesson ids and first/last flags for one lesson."""
    lessons = list(course.lessons)
    lesson_ids = [item.path.name for item in lessons]
    try:
        index = lesson_ids.index(lesson.path.name)
    except ValueError:
        return None, None, True, True

    is_first = index == 0
    is_last = index == len(lessons) - 1
    previous_lesson_id = None if is_first else lessons[index - 1].path.name
    next_lesson_id = None if is_last else lessons[index + 1].path.name
    return previous_lesson_id, next_lesson_id, is_first, is_last


def to_lesson_detail(course: Course, lesson: Lesson) -> LessonDetailDTO:
    """Convert a runtime lesson to a full lesson DTO with course navigation."""
    previous_lesson_id, next_lesson_id, is_first, is_last = _lesson_navigation(
        course,
        lesson,
    )
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
        previous_lesson_id=previous_lesson_id,
        next_lesson_id=next_lesson_id,
        is_first=is_first,
        is_last=is_last,
    )
