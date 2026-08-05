"""Integration test for AI lesson quality fields persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.course_file_writer import CourseFileWriter
from app.content.course_writer import CourseWriter
from app.content.lesson_builder import LessonCandidate


class LessonQualityFieldsPersistenceIntegrationTests(unittest.TestCase):
    """End-to-end: LessonGenerationResult → CourseWriter → lesson.json."""

    def test_quality_fields_persist_through_writer_pipeline(self) -> None:
        result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Safety Basics",
                    content="Full lesson body text.",
                    practical_task="Inspect the work area before starting.",
                    checklist=("Wear PPE", "Check equipment"),
                    common_mistakes=("Skipping inspection",),
                    key_takeaways=("Safety first",),
                    application_tips=("Apply the checklist daily",),
                )
            ],
            course=GeneratedCourseMetadata(
                language="ru",
                title="Safety Training",
                description="Introductory safety course.",
            ),
        )

        draft = CourseWriter().write(result)

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / draft.slug
            CourseFileWriter().write(draft, course_dir)

            lesson_manifest = json.loads(
                (course_dir / "lesson_01" / "lesson.json").read_text(encoding="utf-8")
            )

        self.assertEqual(draft.lessons[0].practical_task, result.lessons[0].practical_task)
        self.assertEqual(draft.lessons[0].checklist, result.lessons[0].checklist)

        self.assertEqual(lesson_manifest["order"], 1)
        self.assertEqual(lesson_manifest["title"], "Safety Basics")
        self.assertEqual(lesson_manifest["description"], "Full lesson body text.")
        self.assertEqual(
            lesson_manifest["practical_task"],
            "Inspect the work area before starting.",
        )
        self.assertEqual(lesson_manifest["checklist"], ["Wear PPE", "Check equipment"])
        self.assertEqual(lesson_manifest["common_mistakes"], ["Skipping inspection"])
        self.assertEqual(lesson_manifest["key_takeaways"], ["Safety first"])
        self.assertEqual(
            lesson_manifest["application_tips"],
            ["Apply the checklist daily"],
        )
        self.assertIsInstance(lesson_manifest["checklist"], list)
        self.assertIsInstance(lesson_manifest["common_mistakes"], list)
        self.assertIsInstance(lesson_manifest["key_takeaways"], list)
        self.assertIsInstance(lesson_manifest["application_tips"], list)


if __name__ == "__main__":
    unittest.main()
