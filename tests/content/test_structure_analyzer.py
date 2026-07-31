"""Tests for course structure analysis (``app.content.structure_analyzer``)."""

from __future__ import annotations

import unittest

from app.content.structure_analyzer import (
    CourseSection,
    CourseStructure,
    StructureAnalyzer,
)


class StructureAnalyzerTests(unittest.TestCase):
    """Tests for :class:`StructureAnalyzer`."""

    def setUp(self) -> None:
        self.analyzer = StructureAnalyzer()

    def test_empty_text(self) -> None:
        structure = self.analyzer.analyze("")

        self.assertEqual(structure, CourseStructure(sections=[]))

    def test_non_empty_text(self) -> None:
        text = "First paragraph.\n\nSecond paragraph."

        structure = self.analyzer.analyze(text)

        self.assertEqual(len(structure.sections), 1)

    def test_section_title(self) -> None:
        structure = self.analyzer.analyze("Some imported content.")

        self.assertEqual(structure.sections[0].title, "Imported Content")

    def test_content_is_preserved(self) -> None:
        text = "Line one.\nLine two.\n\nParagraph two."

        structure = self.analyzer.analyze(text)

        self.assertEqual(
            structure.sections[0],
            CourseSection(title="Imported Content", content=text),
        )
