"""Tests for lesson candidate building (``app.content.lesson_builder``)."""

from __future__ import annotations

import unittest

from app.content.lesson_builder import LessonBuilder, LessonCandidate
from app.content.structure_analyzer import CourseSection, CourseStructure


class LessonBuilderTests(unittest.TestCase):
    """Tests for :class:`LessonBuilder`."""

    def setUp(self) -> None:
        self.builder = LessonBuilder()

    def test_empty_structure(self) -> None:
        structure = CourseStructure(sections=[])

        self.assertEqual(self.builder.build(structure), [])

    def test_single_section(self) -> None:
        structure = CourseStructure(
            sections=[
                CourseSection(
                    title="Imported Content",
                    content="Some imported content.",
                )
            ]
        )

        self.assertEqual(
            self.builder.build(structure),
            [
                LessonCandidate(
                    title="Imported Content",
                    content="Some imported content.",
                )
            ],
        )

    def test_multiple_sections(self) -> None:
        structure = CourseStructure(
            sections=[
                CourseSection(title="Section 1", content="First block."),
                CourseSection(title="Section 2", content="Second block."),
                CourseSection(title="Section 3", content="Third block."),
            ]
        )

        self.assertEqual(
            self.builder.build(structure),
            [
                LessonCandidate(title="Section 1", content="First block."),
                LessonCandidate(title="Section 2", content="Second block."),
                LessonCandidate(title="Section 3", content="Third block."),
            ],
        )

    def test_section_order_is_preserved(self) -> None:
        structure = CourseStructure(
            sections=[
                CourseSection(title="Section 1", content="Alpha."),
                CourseSection(title="Section 2", content="Beta."),
                CourseSection(title="Section 3", content="Gamma."),
            ]
        )

        candidates = self.builder.build(structure)

        self.assertEqual(
            [candidate.content for candidate in candidates],
            ["Alpha.", "Beta.", "Gamma."],
        )
        self.assertEqual(
            [candidate.title for candidate in candidates],
            ["Section 1", "Section 2", "Section 3"],
        )

    def test_title_and_content_are_copied_unchanged(self) -> None:
        title = "  Custom Title  "
        content = "Line one.\nLine two."
        structure = CourseStructure(
            sections=[
                CourseSection(title=title, content=content),
            ]
        )

        candidate = self.builder.build(structure)[0]

        self.assertEqual(candidate.title, title)
        self.assertEqual(candidate.content, content)
