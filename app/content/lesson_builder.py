"""Lesson candidate builder for the import pipeline.

Maps a :class:`CourseStructure` into a list of :class:`LessonCandidate`
objects ready for downstream course generation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.content.structure_analyzer import CourseStructure


@dataclass(frozen=True)
class LessonCandidate:
    """A lesson derived from a course structure section."""

    title: str
    content: str


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
