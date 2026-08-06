"""Tests for course file writing (``app.content.course_file_writer``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.content.course_file_writer import CourseFileWriter
from app.content.course_writer import CourseDraft
from app.content.lesson_builder import LessonCandidate
from app.content.practical_task import PracticalTask


def _sample_draft() -> CourseDraft:
    return CourseDraft(
        slug="safety-training",
        title="Safety Training",
        description="Introductory safety course.",
        language="ru",
        lessons=(
            LessonCandidate(
                title="Lesson One",
                content="Full lesson body for lesson one.",
                summary="First summary.",
                learning_objectives=("Objective A", "Objective B"),
                practical_task="Inspect the work area before starting.",
                checklist=("Wear PPE", "Check equipment"),
                common_mistakes=("Skipping inspection",),
                key_takeaways=("Safety first",),
                application_tips=("Apply the checklist daily",),
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

    def test_writes_lesson_json_with_runtime_contract_fields(self) -> None:
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
                    "order": 1,
                    "title": "Lesson One",
                    "description": "Full lesson body for lesson one.",
                    "practical_task": "Inspect the work area before starting.",
                    "structured_practical_task": None,
                    "checklist": ["Wear PPE", "Check equipment"],
                    "common_mistakes": ["Skipping inspection"],
                    "key_takeaways": ["Safety first"],
                    "application_tips": ["Apply the checklist daily"],
                },
            )
            self.assertEqual(
                second_lesson,
                {
                    "order": 2,
                    "title": "Lesson Two",
                    "description": "Second lesson body.",
                    "practical_task": "",
                    "structured_practical_task": None,
                    "checklist": [],
                    "common_mistakes": [],
                    "key_takeaways": [],
                    "application_tips": [],
                },
            )
            self.assertNotIn("number", first_lesson)
            self.assertNotIn("summary", first_lesson)
            self.assertNotIn("learning_objectives", first_lesson)
            self.assertNotIn("content", first_lesson)

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
            self.assertEqual(third_lesson["order"], 3)
            self.assertEqual(third_lesson["title"], "Gamma")
            self.assertEqual(third_lesson["description"], "gamma body")

    def test_legacy_lesson_writes_content_as_description(self) -> None:
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

            self.assertEqual(lesson_manifest["order"], 1)
            self.assertEqual(lesson_manifest["title"], "Legacy Lesson")
            self.assertEqual(
                lesson_manifest["description"],
                "Legacy content only.",
            )
            self.assertEqual(lesson_manifest["practical_task"], "")
            self.assertIsNone(lesson_manifest["structured_practical_task"])
            self.assertEqual(lesson_manifest["checklist"], [])
            self.assertEqual(lesson_manifest["common_mistakes"], [])
            self.assertEqual(lesson_manifest["key_takeaways"], [])
            self.assertEqual(lesson_manifest["application_tips"], [])
            self.assertNotIn("number", lesson_manifest)
            self.assertNotIn("summary", lesson_manifest)
            self.assertNotIn("learning_objectives", lesson_manifest)
            self.assertNotIn("content", lesson_manifest)

    def test_writes_empty_ai_fields_as_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "defaults-course"
            draft = CourseDraft(
                slug="defaults-course",
                title="Defaults Course",
                description="",
                language="en",
                lessons=(
                    LessonCandidate(
                        title="Minimal Lesson",
                        content="Minimal body.",
                    ),
                ),
            )

            self.writer.write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertEqual(lesson_manifest["practical_task"], "")
            self.assertIsNone(lesson_manifest["structured_practical_task"])
            self.assertEqual(lesson_manifest["checklist"], [])
            self.assertEqual(lesson_manifest["common_mistakes"], [])
            self.assertEqual(lesson_manifest["key_takeaways"], [])
            self.assertEqual(lesson_manifest["application_tips"], [])

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

    def test_writes_structured_practical_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "structured-task-course"
            draft = CourseDraft(
                slug="structured-task-course",
                title="Structured Task Course",
                description="",
                language="ru",
                lessons=(
                    LessonCandidate(
                        title="Lesson One",
                        content="Lesson body.",
                        structured_practical_task=PracticalTask(
                            title="Проверка рабочего места",
                            description="Осмотрите рабочую зону перед началом смены.",
                            expected_result="Все риски обнаружены и устранены.",
                            estimated_minutes=10,
                        ),
                    ),
                ),
            )

            self.writer.write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                lesson_manifest["structured_practical_task"],
                {
                    "title": "Проверка рабочего места",
                    "description": "Осмотрите рабочую зону перед началом смены.",
                    "expected_result": "Все риски обнаружены и устранены.",
                    "estimated_minutes": 10,
                },
            )

    def test_writes_null_structured_practical_task_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "no-structured-task"
            draft = CourseDraft(
                slug="no-structured-task",
                title="No Structured Task",
                description="",
                language="en",
                lessons=(
                    LessonCandidate(
                        title="Lesson One",
                        content="Body.",
                    ),
                ),
            )

            self.writer.write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertIn("structured_practical_task", lesson_manifest)
            self.assertIsNone(lesson_manifest["structured_practical_task"])

    def test_writes_null_estimated_minutes_in_structured_practical_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "no-estimate-course"
            draft = CourseDraft(
                slug="no-estimate-course",
                title="No Estimate Course",
                description="",
                language="en",
                lessons=(
                    LessonCandidate(
                        title="Lesson One",
                        content="Body.",
                        structured_practical_task=PracticalTask(
                            title="Task title",
                            description="Task description.",
                            expected_result="Expected outcome.",
                        ),
                    ),
                ),
            )

            self.writer.write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                lesson_manifest["structured_practical_task"],
                {
                    "title": "Task title",
                    "description": "Task description.",
                    "expected_result": "Expected outcome.",
                    "estimated_minutes": None,
                },
            )

    def test_legacy_and_structured_practical_task_coexist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "coexist-course"
            draft = CourseDraft(
                slug="coexist-course",
                title="Coexist Course",
                description="",
                language="en",
                lessons=(
                    LessonCandidate(
                        title="Lesson One",
                        content="Body.",
                        practical_task="Legacy task",
                        structured_practical_task=PracticalTask(
                            title="Structured title",
                            description="Structured description.",
                            expected_result="Structured result.",
                            estimated_minutes=5,
                        ),
                    ),
                ),
            )

            self.writer.write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

            self.assertEqual(lesson_manifest["practical_task"], "Legacy task")
            self.assertEqual(
                lesson_manifest["structured_practical_task"],
                {
                    "title": "Structured title",
                    "description": "Structured description.",
                    "expected_result": "Structured result.",
                    "estimated_minutes": 5,
                },
            )


if __name__ == "__main__":
    unittest.main()
