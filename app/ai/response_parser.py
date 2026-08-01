"""Parse AI model responses into structured lesson generation results."""

from __future__ import annotations

import json
from typing import Any

from app.ai.interfaces import LessonGenerationResult
from app.content.lesson_builder import LessonCandidate


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

        if "lessons" not in data:
            raise ValueError("Response does not contain 'lessons'.")

        raw_lessons = data["lessons"]
        if not isinstance(raw_lessons, list):
            raise ValueError("Field 'lessons' must be a list.")

        lessons: list[LessonCandidate] = []
        for index, item in enumerate(raw_lessons):
            lessons.append(_parse_lesson_item(item, index))

        return LessonGenerationResult(lessons=lessons)


def _parse_lesson_item(item: Any, index: int) -> LessonCandidate:
    if not isinstance(item, dict):
        raise ValueError(f"Lesson at index {index} must be a JSON object.")

    if "title" not in item:
        raise ValueError(f"Lesson at index {index} is missing 'title'.")

    if "content" not in item:
        raise ValueError(f"Lesson at index {index} is missing 'content'.")

    return LessonCandidate(
        title=item["title"],
        content=item["content"],
    )
