"""Integration tests for the AI course generation pipeline."""

from __future__ import annotations

import unittest

from app.ai.interfaces import LessonGenerationRequest
from app.ai.mock_provider import MockCourseGenerationAI
from app.ai.service import CourseGenerationService
from app.content.lesson_builder import LessonBuilder
from app.content.structure_analyzer import CourseSection, CourseStructure


class CourseGenerationPipelineIntegrationTests(unittest.TestCase):
    """End-to-end tests for LessonBuilder and CourseGenerationService."""

    def test_two_sections_flow_through_mock_provider_unchanged(self) -> None:
        structure = CourseStructure(
            sections=[
                CourseSection(title="Section 1", content="First section."),
                CourseSection(title="Section 2", content="Second section."),
            ]
        )
        builder = LessonBuilder()
        provider = MockCourseGenerationAI()
        service = CourseGenerationService(provider)

        candidates = builder.build(structure)
        request = LessonGenerationRequest(lessons=candidates)
        result = service.generate_lessons(request)

        self.assertEqual(len(result.lessons), 2)
        self.assertEqual(result.lessons[0].title, "Section 1")
        self.assertEqual(result.lessons[0].content, "First section.")
        self.assertEqual(result.lessons[1].title, "Section 2")
        self.assertEqual(result.lessons[1].content, "Second section.")
        self.assertEqual(
            [lesson.title for lesson in result.lessons],
            [candidate.title for candidate in candidates],
        )
        self.assertEqual(
            [lesson.content for lesson in result.lessons],
            [candidate.content for candidate in candidates],
        )

    def test_empty_structure_returns_empty_lessons(self) -> None:
        structure = CourseStructure(sections=[])
        builder = LessonBuilder()
        provider = MockCourseGenerationAI()
        service = CourseGenerationService(provider)

        candidates = builder.build(structure)
        request = LessonGenerationRequest(lessons=candidates)
        result = service.generate_lessons(request)

        self.assertEqual(candidates, [])
        self.assertEqual(result.lessons, [])


if __name__ == "__main__":
    unittest.main()
