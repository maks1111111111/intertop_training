"""Tests for AI response parser (``app.ai.response_parser``)."""

from __future__ import annotations

import json
import unittest

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
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

    def test_legacy_json_with_course_title(self) -> None:
        response = json.dumps(
            {
                "course_title": "Legacy Course",
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "First lesson content.",
                    }
                ],
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

    def test_extended_json_with_course_summary_and_content(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Safety Training",
                    "description": "Introductory safety course.",
                    "language": "en",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "First lesson summary.",
                        "content": "First lesson full content.",
                        "learning_objectives": [
                            "Objective A",
                            "Objective B",
                        ],
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(len(result.lessons), 1)
        self.assertEqual(
            result.course,
            GeneratedCourseMetadata(
                title="Safety Training",
                description="Introductory safety course.",
                language="en",
            ),
        )
        self.assertEqual(result.lessons[0].title, "Lesson One")
        self.assertEqual(result.lessons[0].summary, "First lesson summary.")
        self.assertEqual(result.lessons[0].content, "First lesson full content.")
        self.assertNotEqual(result.lessons[0].content, "")
        self.assertEqual(
            result.lessons[0].learning_objectives,
            ("Objective A", "Objective B"),
        )

    def test_extended_json_with_course_and_summary(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Safety Training",
                    "description": "Introductory safety course.",
                    "language": "en",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "First lesson summary.",
                        "learning_objectives": [
                            "Objective A",
                            "Objective B",
                        ],
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(len(result.lessons), 1)
        self.assertEqual(
            result.course,
            GeneratedCourseMetadata(
                title="Safety Training",
                description="Introductory safety course.",
                language="en",
            ),
        )
        self.assertEqual(result.lessons[0].title, "Lesson One")
        self.assertEqual(result.lessons[0].summary, "First lesson summary.")
        self.assertEqual(result.lessons[0].content, "")
        self.assertEqual(
            result.lessons[0].learning_objectives,
            ("Objective A", "Objective B"),
        )

    def test_summary_without_learning_objectives(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Course",
                    "description": "Description.",
                    "language": "ru",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "Summary only.",
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(
            result.course,
            GeneratedCourseMetadata(
                title="Course",
                description="Description.",
                language="ru",
            ),
        )
        self.assertEqual(result.lessons[0].summary, "Summary only.")
        self.assertEqual(result.lessons[0].content, "")
        self.assertEqual(result.lessons[0].learning_objectives, ())

    def test_invalid_course_title_type_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "course_title": 123,
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "Content.",
                    }
                ],
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Field 'course_title' must be a string.",
        )

    def test_course_language_ru_is_accepted(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Course",
                    "description": "Description.",
                    "language": "ru",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "Summary.",
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(result.course.language, "ru")

    def test_course_language_kk_is_accepted(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Course",
                    "description": "Description.",
                    "language": "kk",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "Summary.",
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(result.course.language, "kk")

    def test_course_language_en_is_accepted(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Course",
                    "description": "Description.",
                    "language": "en",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "Summary.",
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        self.assertEqual(result.course.language, "en")

    def test_unknown_course_language_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Course",
                    "description": "Description.",
                    "language": "de",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "Summary.",
                    }
                ],
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Field 'course.language' must be one of: en, kk, ru.",
        )

    def test_missing_course_language_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Course",
                    "description": "Description.",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "Summary.",
                    }
                ],
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Field 'course.language' is required.",
        )

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
            "Lesson at index 0 is missing 'summary' or 'content'.",
        )

    def test_invalid_json_raises_json_decode_error(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            self.parser.parse_lessons("{not valid json")

    def test_full_extended_json_with_quality_fields(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Safety Training",
                    "description": "Introductory safety course.",
                    "language": "en",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "First lesson summary.",
                        "content": "First lesson full content.",
                        "learning_objectives": ["Objective A"],
                        "practical_task": "Inspect the work area.",
                        "checklist": ["Check exits", "Verify equipment"],
                        "common_mistakes": ["Skipping inspection"],
                        "key_takeaways": ["Safety first"],
                        "application_tips": ["Review checklist daily"],
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        lesson = result.lessons[0]
        self.assertEqual(lesson.practical_task, "Inspect the work area.")
        self.assertEqual(lesson.checklist, ("Check exits", "Verify equipment"))
        self.assertEqual(lesson.common_mistakes, ("Skipping inspection",))
        self.assertEqual(lesson.key_takeaways, ("Safety first",))
        self.assertEqual(lesson.application_tips, ("Review checklist daily",))

    def test_extended_json_without_quality_fields_uses_defaults(self) -> None:
        response = json.dumps(
            {
                "course": {
                    "title": "Safety Training",
                    "description": "Introductory safety course.",
                    "language": "en",
                },
                "lessons": [
                    {
                        "title": "Lesson One",
                        "summary": "First lesson summary.",
                        "content": "First lesson full content.",
                        "learning_objectives": ["Objective A"],
                    }
                ],
            }
        )

        result = self.parser.parse_lessons(response)

        lesson = result.lessons[0]
        self.assertEqual(lesson.practical_task, "")
        self.assertEqual(lesson.checklist, ())
        self.assertEqual(lesson.common_mistakes, ())
        self.assertEqual(lesson.key_takeaways, ())
        self.assertEqual(lesson.application_tips, ())

    def test_practical_task_not_string_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "Content.",
                        "practical_task": 123,
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 field 'practical_task' must be a string.",
        )

    def test_checklist_not_list_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "Content.",
                        "checklist": "not-a-list",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 field 'checklist' must be a list.",
        )

    def test_common_mistakes_item_not_string_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "Content.",
                        "common_mistakes": [123],
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 field 'common_mistakes' item at index 0 "
            "must be a string.",
        )

    def test_key_takeaways_not_list_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "Content.",
                        "key_takeaways": {"takeaway": "one"},
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 field 'key_takeaways' must be a list.",
        )

    def test_application_tips_item_not_string_raises_value_error(self) -> None:
        response = json.dumps(
            {
                "lessons": [
                    {
                        "title": "Lesson One",
                        "content": "Content.",
                        "application_tips": [True],
                    }
                ]
            }
        )

        with self.assertRaises(ValueError) as context:
            self.parser.parse_lessons(response)

        self.assertEqual(
            str(context.exception),
            "Lesson at index 0 field 'application_tips' item at index 0 "
            "must be a string.",
        )


if __name__ == "__main__":
    unittest.main()
