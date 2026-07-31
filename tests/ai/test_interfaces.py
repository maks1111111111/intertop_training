"""Tests for AI provider interfaces (``app.ai.interfaces``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import (
    CourseGenerationAI,
    LessonGenerationRequest,
    LessonGenerationResult,
)
from app.content.lesson_builder import LessonCandidate


class LessonGenerationRequestTests(unittest.TestCase):
    """Tests for :class:`LessonGenerationRequest`."""

    def test_create_request(self) -> None:
        lessons = [
            LessonCandidate(title="Section 1", content="First lesson."),
            LessonCandidate(title="Section 2", content="Second lesson."),
        ]

        request = LessonGenerationRequest(lessons=lessons)

        self.assertEqual(request.lessons, lessons)
        self.assertIsInstance(request.lessons, list)
        self.assertTrue(all(isinstance(lesson, LessonCandidate) for lesson in request.lessons))


class LessonGenerationResultTests(unittest.TestCase):
    """Tests for :class:`LessonGenerationResult`."""

    def test_create_result(self) -> None:
        lessons = [
            LessonCandidate(title="Refined 1", content="Refined content."),
        ]

        result = LessonGenerationResult(lessons=lessons)

        self.assertEqual(result.lessons, lessons)
        self.assertIsInstance(result.lessons, list)
        self.assertTrue(all(isinstance(lesson, LessonCandidate) for lesson in result.lessons))


class CourseGenerationAIProtocolTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationAI` structural typing."""

    def test_protocol_accepts_conforming_implementation(self) -> None:
        class StubAI:
            def generate_lessons(
                self,
                request: LessonGenerationRequest,
            ) -> LessonGenerationResult:
                return LessonGenerationResult(lessons=request.lessons)

        ai: CourseGenerationAI = StubAI()
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        result = ai.generate_lessons(request)

        self.assertEqual(result.lessons, request.lessons)
        self.assertIsInstance(result, LessonGenerationResult)
