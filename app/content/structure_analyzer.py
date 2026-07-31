"""Course structure analysis for the import pipeline.

Provides models and an analyzer that maps aggregated import text
into a :class:`CourseStructure` by splitting on blank-line separators.
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
        """Map import text to a course structure split by blank lines.

        Args:
            text: Aggregated text from the import pipeline.

        Returns:
            An empty structure for empty text, one section titled
            ``Imported Content`` for a single block, or numbered sections
            when multiple blocks are detected.
        """
        if not text:
            return CourseStructure(sections=[])

        blocks = self._split_sections(text)

        if len(blocks) == 1:
            return CourseStructure(
                sections=[
                    CourseSection(
                        title="Imported Content",
                        content=blocks[0],
                    )
                ]
            )

        return CourseStructure(
            sections=[
                CourseSection(
                    title=f"Section {index}",
                    content=block,
                )
                for index, block in enumerate(blocks, start=1)
            ]
        )

    def _split_sections(self, text: str) -> list[str]:
        """Split text into non-empty blocks separated by blank lines."""
        return [block for block in text.split("\n\n") if block]
