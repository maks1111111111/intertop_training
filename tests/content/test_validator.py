"""Tests for course manifest validation in the Content Validator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.content.validator import validate_course


def _create_course_dir(
    courses_dir: Path,
    slug: str = "test",
    *,
    course_manifest: Optional[dict] = None,
) -> Path:
    """Create a minimal course directory for validator tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    manifest = course_manifest if course_manifest is not None else {}
    (course_dir / "course.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text("{}", encoding="utf-8")

    return course_dir


def _status_errors(report):
    """Return status-related errors from a validation report."""
    return [
        issue
        for issue in report.errors
        if issue.code in {"course_status_invalid_type", "invalid_course_status"}
    ]


class CourseStatusValidationTests(unittest.TestCase):
    """Validation of optional ``status`` field in ``course.json``."""

    def test_missing_status_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            report = validate_course(course_dir)

        self.assertEqual(_status_errors(report), [])

    def test_published_status_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "published"},
            )
            report = validate_course(course_dir)

        self.assertEqual(_status_errors(report), [])

    def test_draft_status_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft"},
            )
            report = validate_course(course_dir)

        self.assertEqual(_status_errors(report), [])

    def test_archived_status_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "archived"},
            )
            report = validate_course(course_dir)

        self.assertEqual(_status_errors(report), [])

    def test_non_string_status_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": 123},
            )
            report = validate_course(course_dir)

        status_errors = _status_errors(report)
        self.assertEqual(len(status_errors), 1)
        issue = status_errors[0]
        self.assertEqual(issue.code, "course_status_invalid_type")
        self.assertEqual(issue.path, course_dir / "course.json")
        self.assertEqual(issue.location, "status")

    def test_unknown_status_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "active"},
            )
            report = validate_course(course_dir)

        status_errors = _status_errors(report)
        self.assertEqual(len(status_errors), 1)
        issue = status_errors[0]
        self.assertEqual(issue.code, "invalid_course_status")
        self.assertEqual(issue.path, course_dir / "course.json")
        self.assertEqual(issue.location, "status")
        self.assertIn(
            "allowed values are archived, draft, published",
            issue.message,
        )


if __name__ == "__main__":
    unittest.main()
