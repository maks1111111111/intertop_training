"""Integration tests for end-to-end imported text generation."""

from __future__ import annotations

import unittest

from app.ai.mock_provider import MockCourseGenerationAI
from app.ai.service import CourseGenerationService
from app.content.structure_analyzer import StructureAnalyzer
from app.services.course_generation_flow_service import (
    CourseGenerationFlowService,
)
from app.services.course_generation_pipeline_service import (
    CourseGenerationPipelineService,
)
from app.services.imported_text_generation_service import (
    ImportedTextGenerationService,
)


class ImportedTextGenerationIntegrationTests(unittest.TestCase):
    """End-to-end tests for imported text through the AI generation pipeline."""

    def _build_service(self) -> ImportedTextGenerationService:
        provider = MockCourseGenerationAI()
        generation_service = CourseGenerationService(provider)
        pipeline_service = CourseGenerationPipelineService(generation_service)
        flow_service = CourseGenerationFlowService(pipeline_service)
        return ImportedTextGenerationService(
            flow_service=flow_service,
            structure_analyzer=StructureAnalyzer(),
        )

    def test_three_sections_flow_through_full_pipeline_unchanged(self) -> None:
        text = "Introduction\n\nSafety rules\n\nCustomer service"
        service = self._build_service()

        result = service.generate_from_text(text)

        self.assertEqual(len(result.lessons), 3)
        self.assertEqual(result.lessons[0].title, "Section 1")
        self.assertEqual(result.lessons[0].content, "Introduction")
        self.assertEqual(result.lessons[1].title, "Section 2")
        self.assertEqual(result.lessons[1].content, "Safety rules")
        self.assertEqual(result.lessons[2].title, "Section 3")
        self.assertEqual(result.lessons[2].content, "Customer service")
        self.assertEqual(
            [lesson.title for lesson in result.lessons],
            ["Section 1", "Section 2", "Section 3"],
        )
        self.assertEqual(
            [lesson.content for lesson in result.lessons],
            ["Introduction", "Safety rules", "Customer service"],
        )

    def test_empty_text_returns_empty_lessons(self) -> None:
        service = self._build_service()

        result = service.generate_from_text("")

        self.assertEqual(result.lessons, [])


if __name__ == "__main__":
    unittest.main()
