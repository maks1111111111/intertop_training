"""Tests for mock AI provider (``app.ai.mock_provider``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import LessonGenerationRequest, LessonGenerationResult
from app.ai.mock_provider import MockCourseGenerationAI
from app.content.lesson_builder import LessonCandidate


class MockCourseGenerationAITests(unittest.TestCase):
    """Tests for :class:`MockCourseGenerationAI`."""

    def setUp(self) -> None:
        self.provider = MockCourseGenerationAI()

    def test_returns_lesson_generation_result(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        result = self.provider.generate_lessons(request)

        self.assertIsInstance(result, LessonGenerationResult)

    def test_lessons_match_request(self) -> None:
        lessons = [
            LessonCandidate(title="Section 1", content="First."),
            LessonCandidate(title="Section 2", content="Second."),
        ]
        request = LessonGenerationRequest(lessons=lessons)

        result = self.provider.generate_lessons(request)

        self.assertEqual(result.lessons, lessons)

    def test_order_is_preserved(self) -> None:
        lessons = [
            LessonCandidate(title="Section 1", content="Alpha."),
            LessonCandidate(title="Section 2", content="Beta."),
            LessonCandidate(title="Section 3", content="Gamma."),
        ]
        request = LessonGenerationRequest(lessons=lessons)

        result = self.provider.generate_lessons(request)

        self.assertEqual(
            [lesson.content for lesson in result.lessons],
            ["Alpha.", "Beta.", "Gamma."],
        )

    def test_title_not_changed(self) -> None:
        title = "  Custom Title  "
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title=title, content="Content."),
            ]
        )

        result = self.provider.generate_lessons(request)

        self.assertEqual(result.lessons[0].title, title)

    def test_content_not_changed(self) -> None:
        content = "Line one.\nLine two."
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content=content),
            ]
        )

        result = self.provider.generate_lessons(request)

        self.assertEqual(result.lessons[0].content, content)
