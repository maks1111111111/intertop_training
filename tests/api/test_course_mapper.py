"""Tests for course DTO mappers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.api.mappers import course_mapper
from app.content.runtime import ContentRuntime


def _write_course(
    courses_dir: Path,
    slug: str,
    *,
    title: str = "Sample Course",
    description: str = "Course overview for learners.",
    language: str = "ru",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        (
            '{"title": "'
            + title
            + '", "description": "'
            + description
            + '", "status": "published", "language": "'
            + language
            + '"}'
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        '{"title": "First lesson", "order": 1, "description": "Body text."}',
        encoding="utf-8",
    )


class CourseMapperTests(unittest.TestCase):
    """Verify runtime-to-DTO mapping."""

    def test_to_summary_maps_core_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course(courses_dir, "alpha", title="Alpha Course")
            runtime = ContentRuntime(courses_dir)
            course = runtime.get_course("alpha")

        self.assertIsNotNone(course)
        assert course is not None

        summary = course_mapper.to_summary(course)

        self.assertEqual(summary.slug, "alpha")
        self.assertEqual(summary.title, "Alpha Course")
        self.assertEqual(summary.description, "Course overview for learners.")

    def test_to_summary_list_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course(courses_dir, "beta", title="Beta Course")
            _write_course(courses_dir, "alpha", title="Alpha Course")
            runtime = ContentRuntime(courses_dir)

            listing = course_mapper.to_summary_list(runtime.get_courses())

        self.assertEqual(len(listing.items), 2)
        self.assertEqual(listing.items[0].slug, "alpha")
        self.assertEqual(listing.items[1].slug, "beta")

    def test_to_detail_maps_lessons_without_content_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course(courses_dir, "alpha", title="Alpha Course", language="ru")
            runtime = ContentRuntime(courses_dir)
            course = runtime.get_course("alpha")

        self.assertIsNotNone(course)
        assert course is not None

        detail = course_mapper.to_detail(course)

        self.assertEqual(detail.slug, "alpha")
        self.assertEqual(detail.title, "Alpha Course")
        self.assertEqual(detail.description, "Course overview for learners.")
        self.assertEqual(detail.language, "ru")
        self.assertEqual(len(detail.lessons), 1)
        self.assertEqual(detail.lessons[0].id, "lesson_01")
        self.assertEqual(detail.lessons[0].title, "First lesson")
        self.assertEqual(detail.lessons[0].order, 1)


if __name__ == "__main__":
    unittest.main()
