"""Course structure analysis for the import pipeline.

Provides models and a temporary analyzer that maps aggregated import text
into a :class:`CourseStructure`. Real section detection will be added later.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CourseSection:
    """A titled section of imported course content."""

    title: str
    content: str


@dataclass
class CourseStructure:
    """Structured representation of imported course content."""

    sections: list[CourseSection] = field(default_factory=list)


class StructureAnalyzer:
    """Analyze aggregated import text into course sections."""

    def analyze(self, text: str) -> CourseStructure:
        """Map import text to a temporary single-section course structure.

        Args:
            text: Aggregated text from the import pipeline.

        Returns:
            An empty structure for empty text, otherwise one section titled
            ``Imported Content`` containing the original text unchanged.
        """
        if not text:
            return CourseStructure(sections=[])

        return CourseStructure(
            sections=[
                CourseSection(
                    title="Imported Content",
                    content=text,
                )
            ]
        )
