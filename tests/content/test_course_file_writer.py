"""Tests for course file writing (``app.content.course_file_writer``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.content.course_file_writer import CourseFileWriter
from app.content.course_writer import CourseDraft
from app.content.lesson_builder import LessonCandidate


def _sample_draft() -> CourseDraft:
    return CourseDraft(
        slug="safety-training",
        title="Safety Training",
        description="Introductory safety course.",
        language="ru",
        lessons=(
            LessonCandidate(
                title="Lesson One",
                content="Full lesson body that must not be written.",
                summary="First summary.",
                learning_objectives=("Objective A", "Objective B"),
            ),
            LessonCandidate(
                title="Lesson Two",
                content="Second lesson body.",
                summary="Second summary.",
                learning_objectives=("Objective C",),
            ),
        ),
    )


class CourseFileWriterTests(unittest.TestCase):
    """Tests for :class:`CourseFileWriter`."""

    def setUp(self) -> None:
        self.writer = CourseFileWriter()

    def test_creates_course_directory_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "safety-training"
            self.writer.write(_sample_draft(), course_dir)

            self.assertTrue(course_dir.is_dir())
            self.assertTrue((course_dir / "course.json").is_file())
            self.assertTrue((course_dir / "lesson_01" / "lesson.json").is_file())
            self.assertTrue((course_dir / "lesson_02" / "lesson.json").is_file())

    def test_writes_course_json_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "safety-training"
            self.writer.write(_sample_draft(), course_dir)

            manifest = json.loads(
                (course_dir / "course.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                manifest,
                {
                    "title": "Safety Training",
                    "description": "Introductory safety course.",
                    "language": "ru",
                    "slug": "safety-training",
                },
            )

    def test_writes_lesson_json_metadata_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "safety-training"
            self.writer.write(_sample_draft(), course_dir)

            first_lesson = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )
            second_lesson = json.loads(
                (course_dir / "lesson_02" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                first_lesson,
                {
                    "number": 1,
                    "title": "Lesson One",
                    "summary": "First summary.",
                    "learning_objectives": ["Objective A", "Objective B"],
                },
            )
            self.assertEqual(
                second_lesson,
                {
                    "number": 2,
                    "title": "Lesson Two",
                    "summary": "Second summary.",
                    "learning_objectives": ["Objective C"],
                },
            )
            self.assertNotIn("content", first_lesson)
            self.assertNotIn("content", second_lesson)

    def test_lesson_order_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "ordered-course"
            draft = CourseDraft(
                slug="ordered-course",
                title="Ordered Course",
                description="",
                language="en",
                lessons=(
                    LessonCandidate(title="Alpha", content="alpha body"),
                    LessonCandidate(title="Beta", content="beta body"),
                    LessonCandidate(title="Gamma", content="gamma body"),
                ),
            )

            self.writer.write(draft, course_dir)

            self.assertTrue((course_dir / "lesson_01" / "lesson.json").is_file())
            self.assertTrue((course_dir / "lesson_02" / "lesson.json").is_file())
            self.assertTrue((course_dir / "lesson_03" / "lesson.json").is_file())

            third_lesson = json.loads(
                (course_dir / "lesson_03" / "lesson.json").read_text(encoding="utf-8")
            )
            self.assertEqual(third_lesson["number"], 3)
            self.assertEqual(third_lesson["title"], "Gamma")

    def test_legacy_lesson_uses_empty_summary_and_objectives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "legacy-course"
            draft = CourseDraft(
                slug="legacy-course",
                title="Legacy Course",
                description="",
                language="en",
                lessons=(
                    LessonCandidate(
                        title="Legacy Lesson",
                        content="Legacy content only.",
                    ),
                ),
            )

            self.writer.write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertEqual(lesson_manifest["summary"], "")
            self.assertEqual(lesson_manifest["learning_objectives"], [])
            self.assertNotIn("content", lesson_manifest)

    def test_empty_lessons_writes_only_course_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "empty-course"
            draft = CourseDraft(
                slug="empty-course",
                title="Empty Course",
                description="No lessons yet.",
                language="en",
                lessons=(),
            )

            self.writer.write(draft, course_dir)

            self.assertTrue((course_dir / "course.json").is_file())
            self.assertFalse((course_dir / "lesson_01").exists())

    def test_returns_course_directory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "returned-course"

            result = self.writer.write(_sample_draft(), course_dir)

            self.assertEqual(result, course_dir)

    def test_destination_file_raises_not_a_directory_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "not-a-directory"
            destination.write_text("file", encoding="utf-8")

            with self.assertRaises(NotADirectoryError):
                self.writer.write(_sample_draft(), destination)


if __name__ == "__main__":
    unittest.main()
