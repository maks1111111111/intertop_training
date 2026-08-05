"""Lesson candidate builder for the import pipeline.

Maps a :class:`CourseStructure` into a list of :class:`LessonCandidate`
objects ready for downstream course generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.content.practical_task import PracticalTask
from app.content.structure_analyzer import CourseStructure


@dataclass(frozen=True)
class LessonCandidate:
    """A lesson derived from a course structure section."""

    title: str
    content: str
    summary: Optional[str] = None
    learning_objectives: tuple[str, ...] = ()
    practical_task: str = ""
    structured_practical_task: Optional[PracticalTask] = None
    checklist: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
    key_takeaways: tuple[str, ...] = ()
    application_tips: tuple[str, ...] = ()


class LessonBuilder:
    """Build lesson candidates from analyzed course structure."""

    def build(self, structure: CourseStructure) -> list[LessonCandidate]:
        """Convert course sections into lesson candidates.

        Args:
            structure: Analyzed course structure from the import pipeline.

        Returns:
            An empty list when there are no sections, otherwise one
            :class:`LessonCandidate` per section in original order.
        """
        if not structure.sections:
            return []

        return [
            LessonCandidate(
                title=section.title,
                content=section.content,
            )
            for section in structure.sections
        ]
