"""Tests for lesson candidate building (``app.content.lesson_builder``)."""

from __future__ import annotations

import unittest

from app.content.lesson_builder import LessonBuilder, LessonCandidate
from app.content.practical_task import PracticalTask
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


class LessonCandidateTests(unittest.TestCase):
    """Tests for :class:`LessonCandidate` structured practical task field."""

    def test_created_without_structured_practical_task(self) -> None:
        candidate = LessonCandidate(title="Lesson", content="Body.")

        self.assertIsNone(candidate.structured_practical_task)
        self.assertEqual(candidate.practical_task, "")

    def test_created_with_structured_practical_task(self) -> None:
        task = PracticalTask(
            title="Inspect the area",
            description="Walk through the work zone.",
            expected_result="Hazards are documented.",
            estimated_minutes=15,
        )
        candidate = LessonCandidate(
            title="Lesson",
            content="Body.",
            structured_practical_task=task,
        )

        self.assertIs(candidate.structured_practical_task, task)

    def test_legacy_practical_task_still_works(self) -> None:
        candidate = LessonCandidate(
            title="Lesson",
            content="Body.",
            practical_task="Complete the safety checklist.",
        )

        self.assertEqual(candidate.practical_task, "Complete the safety checklist.")
        self.assertIsNone(candidate.structured_practical_task)

    def test_backward_compatible_defaults(self) -> None:
        candidate = LessonCandidate(title="Lesson", content="Body.")

        self.assertEqual(
            candidate,
            LessonCandidate(
                title="Lesson",
                content="Body.",
                summary=None,
                learning_objectives=(),
                practical_task="",
                structured_practical_task=None,
                checklist=(),
                common_mistakes=(),
                key_takeaways=(),
                application_tips=(),
            ),
        )
