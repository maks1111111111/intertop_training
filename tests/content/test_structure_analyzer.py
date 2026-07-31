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

    def test_single_block(self) -> None:
        text = "Some imported content."

        structure = self.analyzer.analyze(text)

        self.assertEqual(len(structure.sections), 1)
        self.assertEqual(structure.sections[0].title, "Imported Content")
        self.assertEqual(structure.sections[0].content, text)

    def test_two_blocks(self) -> None:
        structure = self.analyzer.analyze("First block.\n\nSecond block.")

        self.assertEqual(
            structure.sections,
            [
                CourseSection(title="Section 1", content="First block."),
                CourseSection(title="Section 2", content="Second block."),
            ],
        )

    def test_three_blocks(self) -> None:
        structure = self.analyzer.analyze(
            "Alpha.\n\nBeta.\n\nGamma.",
        )

        self.assertEqual(len(structure.sections), 3)
        self.assertEqual(structure.sections[0].title, "Section 1")
        self.assertEqual(structure.sections[1].title, "Section 2")
        self.assertEqual(structure.sections[2].title, "Section 3")
        self.assertEqual(structure.sections[0].content, "Alpha.")
        self.assertEqual(structure.sections[1].content, "Beta.")
        self.assertEqual(structure.sections[2].content, "Gamma.")

    def test_empty_blocks_are_ignored(self) -> None:
        structure = self.analyzer.analyze("Start.\n\n\n\nEnd.")

        self.assertEqual(
            structure.sections,
            [
                CourseSection(title="Section 1", content="Start."),
                CourseSection(title="Section 2", content="End."),
            ],
        )

    def test_block_order_is_preserved(self) -> None:
        structure = self.analyzer.analyze(
            "One.\n\nTwo.\n\nThree.",
        )

        self.assertEqual(
            [section.content for section in structure.sections],
            ["One.", "Two.", "Three."],
        )
