"""Tests for AI response parser (``app.ai.response_parser``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import LessonGenerationResult
from app.ai.response_parser import AIResponseParser


class AIResponseParserTests(unittest.TestCase):
    """Tests for :class:`AIResponseParser`."""

    def setUp(self) -> None:
        self.parser = AIResponseParser()

    def test_empty_string_returns_empty_result(self) -> None:
        result = self.parser.parse_lessons("")

        self.assertIsInstance(result, LessonGenerationResult)
        self.assertEqual(result.lessons, [])

    def test_non_empty_string_raises_not_implemented_error(self) -> None:
        with self.assertRaises(NotImplementedError) as context:
            self.parser.parse_lessons("Lesson 1:\nTitle: Example")

        self.assertEqual(
            str(context.exception),
            "AI response parsing is not implemented yet.",
        )
