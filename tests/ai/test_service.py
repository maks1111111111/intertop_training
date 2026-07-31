"""Tests for AI service layer (``app.ai.service``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.interfaces import (
    CourseGenerationAI,
    LessonGenerationRequest,
    LessonGenerationResult,
)
from app.ai.service import CourseGenerationService
from app.content.lesson_builder import LessonCandidate


class CourseGenerationServiceTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationService`."""

    def test_generate_lessons_calls_provider(self) -> None:
        provider = MagicMock(spec=CourseGenerationAI)
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )
        expected_result = LessonGenerationResult(lessons=request.lessons)
        provider.generate_lessons.return_value = expected_result
        service = CourseGenerationService(provider)

        service.generate_lessons(request)

        provider.generate_lessons.assert_called_once_with(request)

    def test_generate_lessons_returns_lesson_generation_result(self) -> None:
        provider = MagicMock(spec=CourseGenerationAI)
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )
        expected_result = LessonGenerationResult(lessons=request.lessons)
        provider.generate_lessons.return_value = expected_result
        service = CourseGenerationService(provider)

        result = service.generate_lessons(request)

        self.assertIsInstance(result, LessonGenerationResult)

    def test_generate_lessons_returns_provider_result(self) -> None:
        provider = MagicMock(spec=CourseGenerationAI)
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First."),
                LessonCandidate(title="Section 2", content="Second."),
            ]
        )
        expected_result = LessonGenerationResult(lessons=request.lessons)
        provider.generate_lessons.return_value = expected_result
        service = CourseGenerationService(provider)

        result = service.generate_lessons(request)

        self.assertIs(result, expected_result)

    def test_generate_lessons_calls_provider_once(self) -> None:
        provider = MagicMock(spec=CourseGenerationAI)
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )
        provider.generate_lessons.return_value = LessonGenerationResult(
            lessons=request.lessons
        )
        service = CourseGenerationService(provider)

        service.generate_lessons(request)

        self.assertEqual(provider.generate_lessons.call_count, 1)


if __name__ == "__main__":
    unittest.main()
