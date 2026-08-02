"""Parse AI model responses into structured lesson generation results."""

from __future__ import annotations

import json
from typing import Any, Optional, Tuple

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.lesson_builder import LessonCandidate

_SUPPORTED_LANGUAGES = frozenset({"en", "kk", "ru"})


class AIResponseParser:
    """Convert raw AI text responses into :class:`LessonGenerationResult`."""

    def parse_lessons(self, response: str) -> LessonGenerationResult:
        """Parse model output into lesson generation results.

        An empty response returns an empty result. Non-empty responses must
        be valid JSON matching the structured lesson generation contract.
        """
        if response == "":
            return LessonGenerationResult(lessons=[])

        data = json.loads(response)
        if not isinstance(data, dict):
            raise ValueError("Response root must be a JSON object.")

        course_metadata = None
        if "course" in data:
            course_metadata = _parse_course_block(data["course"])

        if "course_title" in data:
            _parse_legacy_course_title(data["course_title"])

        if "lessons" not in data:
            raise ValueError("Response does not contain 'lessons'.")

        raw_lessons = data["lessons"]
        if not isinstance(raw_lessons, list):
            raise ValueError("Field 'lessons' must be a list.")

        lessons: list[LessonCandidate] = []
        for index, item in enumerate(raw_lessons):
            lessons.append(_parse_lesson_item(item, index))

        return LessonGenerationResult(lessons=lessons, course=course_metadata)


def _parse_legacy_course_title(course_title: Any) -> None:
    if not isinstance(course_title, str):
        raise ValueError("Field 'course_title' must be a string.")


def _parse_course_block(course: Any) -> GeneratedCourseMetadata:
    if not isinstance(course, dict):
        raise ValueError("Field 'course' must be a JSON object.")

    if "language" not in course:
        raise ValueError("Field 'course.language' is required.")

    language = course["language"]
    if not isinstance(language, str) or not language.strip():
        raise ValueError("Field 'course.language' must be a non-empty string.")

    normalized_language = language.strip()
    if normalized_language not in _SUPPORTED_LANGUAGES:
        raise ValueError(
            "Field 'course.language' must be one of: en, kk, ru."
        )

    title = None
    if "title" in course:
        raw_title = course["title"]
        if not isinstance(raw_title, str):
            raise ValueError("Field 'course.title' must be a string.")
        title = raw_title

    description = None
    if "description" in course:
        raw_description = course["description"]
        if not isinstance(raw_description, str):
            raise ValueError("Field 'course.description' must be a string.")
        description = raw_description

    return GeneratedCourseMetadata(
        language=normalized_language,
        title=title,
        description=description,
    )


def _parse_lesson_item(item: Any, index: int) -> LessonCandidate:
    if not isinstance(item, dict):
        raise ValueError(f"Lesson at index {index} must be a JSON object.")

    if "title" not in item:
        raise ValueError(f"Lesson at index {index} is missing 'title'.")

    title = item["title"]
    if not isinstance(title, str):
        raise ValueError(f"Lesson at index {index} field 'title' must be a string.")

    summary, content, learning_objectives = _parse_lesson_fields(item, index)
    return LessonCandidate(
        title=title,
        content=content,
        summary=summary,
        learning_objectives=learning_objectives,
    )


def _parse_lesson_fields(
    item: dict[str, Any],
    index: int,
) -> Tuple[Optional[str], str, Tuple[str, ...]]:
    summary_present = "summary" in item
    content_present = "content" in item

    summary = None
    content = ""

    if summary_present:
        raw_summary = item["summary"]
        if not isinstance(raw_summary, str):
            raise ValueError(
                f"Lesson at index {index} field 'summary' must be a string."
            )
        summary = raw_summary
    elif content_present:
        raw_content = item["content"]
        if not isinstance(raw_content, str):
            raise ValueError(
                f"Lesson at index {index} field 'content' must be a string."
            )
        content = raw_content
    else:
        raise ValueError(
            f"Lesson at index {index} is missing 'summary' or 'content'."
        )

    learning_objectives: tuple[str, ...] = ()
    if "learning_objectives" in item:
        objectives = item["learning_objectives"]
        if not isinstance(objectives, list):
            raise ValueError(
                f"Lesson at index {index} field 'learning_objectives' must be a list."
            )
        validated_objectives: list[str] = []
        for objective_index, objective in enumerate(objectives):
            if not isinstance(objective, str):
                raise ValueError(
                    "Lesson at index "
                    f"{index} learning objective at index {objective_index} "
                    "must be a string."
                )
            validated_objectives.append(objective)
        learning_objectives = tuple(validated_objectives)

    return summary, content, learning_objectives
