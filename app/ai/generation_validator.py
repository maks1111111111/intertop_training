"""Validate AI-generated lesson content quality.

Checks that generated lessons contain the minimum required fields before
persistence or downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.interfaces import LessonGenerationResult


@dataclass(frozen=True)
class GenerationValidationReport:
    """Summary of AI generation quality checks.

    Counts reflect per-lesson failures for required fields and, when
    present, for :attr:`~app.content.lesson_builder.LessonCandidate.structured_practical_task`
    quality fields.
    """

    lessons: int
    empty_contents: int
    empty_summaries: int
    empty_titles: int
    empty_learning_objectives: int
    empty_practical_task_titles: int
    empty_practical_task_descriptions: int
    empty_practical_task_expected_results: int
    invalid_practical_task_estimates: int
    valid: bool


class GenerationValidator:
    """Validate :class:`LessonGenerationResult` for minimum content quality."""

    def validate(self, result: LessonGenerationResult) -> GenerationValidationReport:
        """Check each generated lesson for required non-empty fields.

        A lesson fails when ``title``, ``summary``, or ``content`` is empty
        after stripping, when ``learning_objectives`` has no elements, or
        when ``structured_practical_task`` is present but its ``title``,
        ``description``, or ``expected_result`` is empty after stripping, or
        when ``estimated_minutes`` is not ``None`` and is less than or equal
        to zero.
        """
        empty_titles = 0
        empty_summaries = 0
        empty_contents = 0
        empty_learning_objectives = 0
        empty_practical_task_titles = 0
        empty_practical_task_descriptions = 0
        empty_practical_task_expected_results = 0
        invalid_practical_task_estimates = 0

        for lesson in result.lessons:
            if not lesson.title.strip():
                empty_titles += 1
            if lesson.summary is None or not lesson.summary.strip():
                empty_summaries += 1
            if not lesson.content.strip():
                empty_contents += 1
            if not lesson.learning_objectives:
                empty_learning_objectives += 1

            task = lesson.structured_practical_task
            if task is not None:
                if not task.title.strip():
                    empty_practical_task_titles += 1
                if not task.description.strip():
                    empty_practical_task_descriptions += 1
                if not task.expected_result.strip():
                    empty_practical_task_expected_results += 1
                if (
                    task.estimated_minutes is not None
                    and task.estimated_minutes <= 0
                ):
                    invalid_practical_task_estimates += 1

        valid = (
            empty_titles == 0
            and empty_summaries == 0
            and empty_contents == 0
            and empty_learning_objectives == 0
            and empty_practical_task_titles == 0
            and empty_practical_task_descriptions == 0
            and empty_practical_task_expected_results == 0
            and invalid_practical_task_estimates == 0
        )

        return GenerationValidationReport(
            lessons=len(result.lessons),
            empty_contents=empty_contents,
            empty_summaries=empty_summaries,
            empty_titles=empty_titles,
            empty_learning_objectives=empty_learning_objectives,
            empty_practical_task_titles=empty_practical_task_titles,
            empty_practical_task_descriptions=empty_practical_task_descriptions,
            empty_practical_task_expected_results=empty_practical_task_expected_results,
            invalid_practical_task_estimates=invalid_practical_task_estimates,
            valid=valid,
        )
