"""Validate AI-generated lesson content quality.

Checks that generated lessons contain the minimum required fields before
persistence or downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.interfaces import LessonGenerationResult


@dataclass(frozen=True)
class GenerationValidationReport:
    """Summary of AI generation quality checks."""

    lessons: int
    empty_contents: int
    empty_summaries: int
    empty_titles: int
    empty_learning_objectives: int
    valid: bool


class GenerationValidator:
    """Validate :class:`LessonGenerationResult` for minimum content quality."""

    def validate(self, result: LessonGenerationResult) -> GenerationValidationReport:
        """Check each generated lesson for required non-empty fields.

        A lesson fails when ``title``, ``summary``, or ``content`` is empty
        after stripping, or when ``learning_objectives`` has no elements.
        """
        empty_titles = 0
        empty_summaries = 0
        empty_contents = 0
        empty_learning_objectives = 0

        for lesson in result.lessons:
            if not lesson.title.strip():
                empty_titles += 1
            if lesson.summary is None or not lesson.summary.strip():
                empty_summaries += 1
            if not lesson.content.strip():
                empty_contents += 1
            if not lesson.learning_objectives:
                empty_learning_objectives += 1

        valid = (
            empty_titles == 0
            and empty_summaries == 0
            and empty_contents == 0
            and empty_learning_objectives == 0
        )

        return GenerationValidationReport(
            lessons=len(result.lessons),
            empty_contents=empty_contents,
            empty_summaries=empty_summaries,
            empty_titles=empty_titles,
            empty_learning_objectives=empty_learning_objectives,
            valid=valid,
        )
