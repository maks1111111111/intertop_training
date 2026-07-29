"""Tests for course status lifecycle in the runtime scanner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

from app.services.scanner import get_course, scan_courses

_SENTINEL = object()


def _create_course(
    courses_dir: Path,
    slug: str,
    *,
    status: Any = _SENTINEL,
) -> Path:
    """Create a minimal scannable course directory."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    manifest: dict[str, object] = {"title": f"Course {slug}"}
    if status is not _SENTINEL:
        manifest["status"] = status

    (course_dir / "course.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text("{}", encoding="utf-8")

    return course_dir


class ScannerCourseStatusTests(unittest.TestCase):
    """Public behavior of ``scan_courses`` and ``get_course`` by course status."""

    def test_course_without_status_is_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "no_status")
            courses = scan_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "no_status")
        self.assertEqual(courses[0].status, "published")

    def test_published_course_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "published", status="published")
            courses = scan_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].status, "published")

    def test_draft_course_is_not_returned_by_scan_courses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "draft", status="draft")
            courses = scan_courses(courses_dir)

        self.assertEqual(courses, [])

    def test_archived_course_is_not_returned_by_scan_courses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "archived", status="archived")
            courses = scan_courses(courses_dir)

        self.assertEqual(courses, [])

    def test_get_course_returns_none_for_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "draft", status="draft")
            course = get_course(courses_dir, "draft")

        self.assertIsNone(course)

    def test_get_course_returns_none_for_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "archived", status="archived")
            course = get_course(courses_dir, "archived")

        self.assertIsNone(course)

    def test_invalid_status_does_not_publish_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "invalid", status="preview")
            courses = scan_courses(courses_dir)
            course = get_course(courses_dir, "invalid")

        self.assertEqual(courses, [])
        self.assertIsNone(course)

    def test_non_string_status_does_not_publish_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course(courses_dir, "bad_type", status=1)
            courses = scan_courses(courses_dir)
            course = get_course(courses_dir, "bad_type")

        self.assertEqual(courses, [])
        self.assertIsNone(course)


if __name__ == "__main__":
    unittest.main()
