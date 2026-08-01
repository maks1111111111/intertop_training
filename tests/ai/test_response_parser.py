"""Tests for AI response parser (``app.ai.response_parser``)."""

from __future__ import annotations

import json
import unittest

from app.ai.interfaces import LessonGenerationResult
from app.ai.response_parser import AIResponseParser
from app.content.lesson_builder import LessonCandidate


class AIResponseParserTests(unittest.TestCase):
    """Tests for :class:`AIResponseParser`."""

    def setUp(self) -> None:
        self.parser = AIResponseParser()

    def test_empty_string_returns_empty_result(self) -> None:
        result = self.parser.parse_lessons("")

        self.assertIsInstance(result, LessonGenerationResult)
        self.assertEqual(result.lessons, [])

    def test_valid_json_with_one_lesson(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "First lesson content.",
                    }
                ]
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(
            result,
            LessonGenerationResult(
                lessons=[
                    LessonCandidate(
                        title="Lesson One",
                        content="First lesson content.",
                    )
                ]
            ),
        )

    def test_valid_json_with_multiple_lessons(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "First lesson content.",
                    },
                    {
                        "title": "Lesson Two",
                        "content": "Second lesson content.",
                    },
                ]
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(len(result.lessons), 2)
        self.assertEqual(result.lessons[0].title, "Lesson One")
        self.assertEqual(result.lessons[0].content, "First lesson content.")
        self.assertEqual(result.lessons[1].title, "Lesson Two")
        self.assertEqual(result.lessons[1].content, "Second lesson content.")

    def test_missing_lessons_key_raises_value_error(self) -> None:
        response = json.dumps({"items": []})

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Response does not contain 'lessons'.",
        )

    def test_lessons_not_list_raises_value_error(self) -> None:
        response = json.dumps({"lessons": "not-a-list"})

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Field 'lessons' must be a list.",
        )

    def test_missing_title_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "content": "Content without title.",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 is missing 'title'.",
        )

    def test_missing_content_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Title without content.",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 is missing 'content'.",
        )

    def test_invalid_json_raises_json_decode_error(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            self.parser.parse_lessons("{not valid json")
