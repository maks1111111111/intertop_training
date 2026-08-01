"""Tests for the imported text generation application service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.interfaces import LessonGenerationResult
from app.content.lesson_builder import LessonCandidate
from app.content.structure_analyzer import (
    CourseSection,
    CourseStructure,
    StructureAnalyzer,
)
from app.services.course_generation_flow_service import (
    CourseGenerationFlowService,
)
from app.services.imported_text_generation_service import (
    ImportedTextGenerationService,
)


class ImportedTextGenerationServiceTests(unittest.TestCase):
    """Tests for :class:`ImportedTextGenerationService`."""

    def setUp(self) -> None:
        self.text = "First section.\n\nSecond section."
        self.structure = CourseStructure(
            sections=[
                CourseSection(title="Section 1", content="First section."),
                CourseSection(title="Section 2", content="Second section."),
            ]
        )

    def test_injected_structure_analyzer_is_stored(self) -> None:
        mock_analyzer = MagicMock(spec=StructureAnalyzer)
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)

        service = ImportedTextGenerationService(
            flow_service=mock_flow_service,
            structure_analyzer=mock_analyzer,
        )

        self.assertIs(service._structure_analyzer, mock_analyzer)

    def test_default_structure_analyzer_is_used(self) -> None:
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)

        service = ImportedTextGenerationService(flow_service=mock_flow_service)

        self.assertIsInstance(service._structure_analyzer, StructureAnalyzer)

    def test_analyze_called_once_with_original_text(self) -> None:
        mock_analyzer = MagicMock(spec=StructureAnalyzer)
        mock_analyzer.analyze.return_value = self.structure
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)
        mock_flow_service.generate.return_value = LessonGenerationResult(lessons=[])
        service = ImportedTextGenerationService(
            flow_service=mock_flow_service,
            structure_analyzer=mock_analyzer,
        )

        service.generate_from_text(self.text)

        mock_analyzer.analyze.assert_called_once_with(self.text)

    def test_analyzed_structure_passed_to_flow_service(self) -> None:
        mock_analyzer = MagicMock(spec=StructureAnalyzer)
        mock_analyzer.analyze.return_value = self.structure
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)
        mock_flow_service.generate.return_value = LessonGenerationResult(lessons=[])
        service = ImportedTextGenerationService(
            flow_service=mock_flow_service,
            structure_analyzer=mock_analyzer,
        )

        service.generate_from_text(self.text)

        mock_flow_service.generate.assert_called_once_with(self.structure)

    def test_flow_service_generate_called_once(self) -> None:
        mock_analyzer = MagicMock(spec=StructureAnalyzer)
        mock_analyzer.analyze.return_value = self.structure
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)
        mock_flow_service.generate.return_value = LessonGenerationResult(lessons=[])
        service = ImportedTextGenerationService(
            flow_service=mock_flow_service,
            structure_analyzer=mock_analyzer,
        )

        service.generate_from_text(self.text)

        mock_flow_service.generate.assert_called_once()

    def test_returns_flow_service_result_unchanged(self) -> None:
        mock_analyzer = MagicMock(spec=StructureAnalyzer)
        mock_analyzer.analyze.return_value = self.structure
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)
        expected_result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Generated lesson",
                    content="Generated content.",
                )
            ]
        )
        mock_flow_service.generate.return_value = expected_result
        service = ImportedTextGenerationService(
            flow_service=mock_flow_service,
            structure_analyzer=mock_analyzer,
        )

        result = service.generate_from_text(self.text)

        self.assertIs(result, expected_result)

    def test_empty_text_passes_through_analyzer_and_flow_service(self) -> None:
        mock_analyzer = MagicMock(spec=StructureAnalyzer)
        empty_structure = CourseStructure(sections=[])
        mock_analyzer.analyze.return_value = empty_structure
        mock_flow_service = MagicMock(spec=CourseGenerationFlowService)
        expected_result = LessonGenerationResult(lessons=[])
        mock_flow_service.generate.return_value = expected_result
        service = ImportedTextGenerationService(
            flow_service=mock_flow_service,
            structure_analyzer=mock_analyzer,
        )

        result = service.generate_from_text("")

        mock_analyzer.analyze.assert_called_once_with("")
        mock_flow_service.generate.assert_called_once_with(empty_structure)
        self.assertIs(result, expected_result)


if __name__ == "__main__":
    unittest.main()
