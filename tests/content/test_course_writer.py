"""Tests for course draft writing (``app.content.course_writer``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.course_writer import CourseDraft, CourseWriter
from app.content.lesson_builder import LessonCandidate


class CourseWriterTests(unittest.TestCase):
    """Tests for :class:`CourseWriter`."""

    def setUp(self) -> None:
        self.writer = CourseWriter()

    def test_extended_result_produces_course_draft(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Lesson One",
                    content="",
                    summary="First summary.",
                    learning_objectives=("Objective A",),
                )
            ],
            course=GeneratedCourseMetadata(
                title="Safety Training",
                description="Introductory safety course.",
                language="ru",
            ),
        )

        draft = self.writer.write(result)

        self.assertEqual(
            draft,
            CourseDraft(
                slug="safety-training",
                title="Safety Training",
                description="Introductory safety course.",
                language="ru",
                lessons=tuple(result.lessons),
            ),
        )

    def test_legacy_result_uses_safe_defaults(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Lesson One",
                    content="First lesson content.",
                )
            ],
        )

        draft = self.writer.write(result)

        self.assertEqual(draft.slug, "imported-course")
        self.assertEqual(draft.title, "Imported Course")
        self.assertEqual(draft.description, "")
        self.assertEqual(draft.language, "en")
        self.assertEqual(draft.lessons, tuple(result.lessons))

    def test_empty_lessons_produces_draft_with_empty_lessons(self) -> None:
        result = LessonGenerationResult(
            lessons=[],
            course=GeneratedCourseMetadata(
                title="Empty Course",
                description="No lessons yet.",
                language="en",
            ),
        )

        draft = self.writer.write(result)

        self.assertEqual(draft.lessons, ())
        self.assertEqual(draft.slug, "empty-course")

    def test_slugify_lowercases_and_replaces_spaces(self) -> None:
        result = LessonGenerationResult(
            lessons=[],
            course=GeneratedCourseMetadata(
                title="Brand History & Technology",
                description="",
                language="en",
            ),
        )

        draft = self.writer.write(result)

        self.assertEqual(draft.slug, "brand-history-technology")

    def test_non_latin_title_gets_unique_course_slug(self) -> None:
        result = LessonGenerationResult(
            lessons=[],
            course=GeneratedCourseMetadata(
                title="История брендов",
                description="",
                language="ru",
            ),
        )

        draft = self.writer.write(result)

        self.assertRegex(draft.slug, r"^course-[0-9a-f]{12}$")
        self.assertEqual(draft.title, "История брендов")

    def test_non_latin_titles_receive_distinct_slugs(self) -> None:
        first = self.writer.write(
            LessonGenerationResult(
                lessons=[],
                course=GeneratedCourseMetadata(
                    title="История брендов",
                    description="",
                    language="ru",
                ),
            )
        )
        second = self.writer.write(
            LessonGenerationResult(
                lessons=[],
                course=GeneratedCourseMetadata(
                    title="Қауіпсіздік",
                    description="",
                    language="kk",
                ),
            )
        )

        self.assertRegex(first.slug, r"^course-[0-9a-f]{12}$")
        self.assertRegex(second.slug, r"^course-[0-9a-f]{12}$")
        self.assertNotEqual(first.slug, second.slug)

    def test_lesson_order_and_fields_are_preserved(self) -> None:
        lessons = [
            LessonCandidate(
                title="First",
                content="",
                summary="Summary one.",
                learning_objectives=("A", "B"),
            ),
            LessonCandidate(
                title="Second",
                content="Legacy content.",
            ),
        ]
        result = LessonGenerationResult(
            lessons=lessons,
            course=GeneratedCourseMetadata(
                title="Course",
                description="Description.",
                language="kk",
            ),
        )

        draft = self.writer.write(result)

        self.assertEqual(len(draft.lessons), 2)
        self.assertEqual(draft.lessons[0].title, "First")
        self.assertEqual(draft.lessons[0].summary, "Summary one.")
        self.assertEqual(draft.lessons[0].learning_objectives, ("A", "B"))
        self.assertEqual(draft.lessons[1].title, "Second")
        self.assertEqual(draft.lessons[1].content, "Legacy content.")

    def test_missing_course_title_uses_default_title_and_slug(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Lesson One",
                    content="Content.",
                )
            ],
            course=GeneratedCourseMetadata(
                title=None,
                description="Only description.",
                language="en",
            ),
        )

        draft = self.writer.write(result)

        self.assertEqual(draft.title, "Imported Course")
        self.assertEqual(draft.slug, "imported-course")
        self.assertEqual(draft.description, "Only description.")


if __name__ == "__main__":
    unittest.main()
