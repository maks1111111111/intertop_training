"""Tests for the course generation pipeline application service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.interfaces import LessonGenerationRequest, LessonGenerationResult
from app.ai.service import CourseGenerationService
from app.content.lesson_builder import LessonBuilder, LessonCandidate
from app.content.structure_analyzer import CourseSection, CourseStructure
from app.services.course_generation_pipeline_service import (
    CourseGenerationPipelineService,
)


class CourseGenerationPipelineServiceTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationPipelineService`."""

    def setUp(self) -> None:
        self.structure = CourseStructure(
            sections=[
                CourseSection(title="Section 1", content="First section."),
                CourseSection(title="Section 2", content="Second section."),
            ]
        )
        self.candidates = [
            LessonCandidate(title="Section 1", content="First section."),
            LessonCandidate(title="Section 2", content="Second section."),
        ]

    def test_injected_lesson_builder_is_stored(self) -> None:
        mock_builder = MagicMock(spec=LessonBuilder)
        mock_service = MagicMock(spec=CourseGenerationService)

        service = CourseGenerationPipelineService(
            generation_service=mock_service,
            lesson_builder=mock_builder,
        )

        self.assertIs(service._lesson_builder, mock_builder)

    def test_default_lesson_builder_is_used(self) -> None:
        mock_service = MagicMock(spec=CourseGenerationService)

        service = CourseGenerationPipelineService(generation_service=mock_service)

        self.assertIsInstance(service._lesson_builder, LessonBuilder)

    def test_lesson_builder_build_called_once_with_structure(self) -> None:
        mock_builder = MagicMock(spec=LessonBuilder)
        mock_builder.build.return_value = self.candidates
        mock_service = MagicMock(spec=CourseGenerationService)
        mock_service.generate_lessons.return_value = LessonGenerationResult(
            lessons=self.candidates
        )
        service = CourseGenerationPipelineService(
            generation_service=mock_service,
            lesson_builder=mock_builder,
        )

        service.generate_lessons(self.structure)

        mock_builder.build.assert_called_once_with(self.structure)

    def test_generation_service_called_once(self) -> None:
        mock_builder = MagicMock(spec=LessonBuilder)
        mock_builder.build.return_value = self.candidates
        mock_service = MagicMock(spec=CourseGenerationService)
        mock_service.generate_lessons.return_value = LessonGenerationResult(
            lessons=self.candidates
        )
        service = CourseGenerationPipelineService(
            generation_service=mock_service,
            lesson_builder=mock_builder,
        )

        service.generate_lessons(self.structure)

        mock_service.generate_lessons.assert_called_once()

    def test_generation_service_receives_request_with_builder_candidates(self) -> None:
        mock_builder = MagicMock(spec=LessonBuilder)
        mock_builder.build.return_value = self.candidates
        mock_service = MagicMock(spec=CourseGenerationService)
        mock_service.generate_lessons.return_value = LessonGenerationResult(
            lessons=self.candidates
        )
        service = CourseGenerationPipelineService(
            generation_service=mock_service,
            lesson_builder=mock_builder,
        )

        service.generate_lessons(self.structure)

        expected_request = LessonGenerationRequest(lessons=self.candidates)
        mock_service.generate_lessons.assert_called_once_with(expected_request)

    def test_returns_generation_service_result_unchanged(self) -> None:
        mock_builder = MagicMock(spec=LessonBuilder)
        mock_builder.build.return_value = self.candidates
        mock_service = MagicMock(spec=CourseGenerationService)
        expected_result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Generated lesson",
                    content="Generated content.",
                )
            ]
        )
        mock_service.generate_lessons.return_value = expected_result
        service = CourseGenerationPipelineService(
            generation_service=mock_service,
            lesson_builder=mock_builder,
        )

        result = service.generate_lessons(self.structure)

        self.assertIs(result, expected_result)


if __name__ == "__main__":
    unittest.main()
