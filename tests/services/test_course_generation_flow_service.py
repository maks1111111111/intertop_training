"""Tests for the course generation flow application service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.interfaces import LessonGenerationResult
from app.content.lesson_builder import LessonCandidate
from app.content.structure_analyzer import CourseSection, CourseStructure
from app.services.course_generation_flow_service import (
    CourseGenerationFlowService,
)
from app.services.course_generation_pipeline_service import (
    CourseGenerationPipelineService,
)


class CourseGenerationFlowServiceTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationFlowService`."""

    def setUp(self) -> None:
        self.structure = CourseStructure(
            sections=[
                CourseSection(title="Section 1", content="First section."),
                CourseSection(title="Section 2", content="Second section."),
            ]
        )

    def test_generate_calls_pipeline_service_once(self) -> None:
        pipeline_service = MagicMock(spec=CourseGenerationPipelineService)
        pipeline_service.generate_lessons.return_value = LessonGenerationResult(
            lessons=[]
        )
        flow_service = CourseGenerationFlowService(pipeline_service)

        flow_service.generate(self.structure)

        pipeline_service.generate_lessons.assert_called_once_with(self.structure)

    def test_generate_passes_structure_unchanged(self) -> None:
        pipeline_service = MagicMock(spec=CourseGenerationPipelineService)
        pipeline_service.generate_lessons.return_value = LessonGenerationResult(
            lessons=[]
        )
        flow_service = CourseGenerationFlowService(pipeline_service)

        flow_service.generate(self.structure)

        call_args = pipeline_service.generate_lessons.call_args
        self.assertIs(call_args.args[0], self.structure)

    def test_generate_returns_pipeline_service_result_unchanged(self) -> None:
        pipeline_service = MagicMock(spec=CourseGenerationPipelineService)
        expected_result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Generated lesson",
                    content="Generated content.",
                )
            ]
        )
        pipeline_service.generate_lessons.return_value = expected_result
        flow_service = CourseGenerationFlowService(pipeline_service)

        result = flow_service.generate(self.structure)

        self.assertIs(result, expected_result)


if __name__ == "__main__":
    unittest.main()
