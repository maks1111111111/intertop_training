"""Tests for the Content Validator CLI (``app.content.cli``)."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from app.content.cli import main


def _create_valid_course(courses_dir: Path, slug: str = "valid") -> Path:
    """Create a minimal course that passes structural validation."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text("{}", encoding="utf-8")
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text("{}", encoding="utf-8")
    return course_dir


def _create_course_with_warning(courses_dir: Path, slug: str = "warning") -> Path:
    """Create a course that triggers a warning but no errors."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text("{}", encoding="utf-8")
    return course_dir


def _create_course_with_duplicate_order(
    courses_dir: Path,
    slug: str = "error",
) -> Path:
    """Create a course with duplicate lesson order values."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text("{}", encoding="utf-8")
    for lesson_slug in ("lesson_01", "lesson_02"):
        lesson_dir = course_dir / lesson_slug
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            '{"order": 1}',
            encoding="utf-8",
        )
    return course_dir


def _run_cli(courses_dir: Path) -> tuple[int, str]:
    """Run the CLI against ``courses_dir`` and capture stdout."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = main([str(courses_dir)])
    return exit_code, stdout.getvalue()


class ContentCliTests(unittest.TestCase):
    """Integration tests for ``app.content.cli.main``."""

    def test_empty_courses_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Summary:", output)
        self.assertIn("Courses: 0", output)
        self.assertIn("Errors: 0", output)
        self.assertIn("Warnings: 0", output)

    def test_missing_courses_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = Path(tmp) / "missing"
            exit_code, output = _run_cli(missing_dir)

        self.assertEqual(exit_code, 2)
        self.assertIn("does not exist or is not a directory", output)

    def test_valid_course_without_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_valid_course(courses_dir, slug="valid")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Course: valid", output)
        self.assertIn("  OK", output)
        self.assertIn("Courses: 1", output)
        self.assertIn("Errors: 0", output)
        self.assertIn("Warnings: 0", output)

    def test_course_with_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course_with_warning(courses_dir, slug="warning")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("WARNING", output)
        self.assertIn("course_without_lessons", output)
        self.assertIn("Courses: 1", output)
        self.assertIn("Errors: 0", output)
        self.assertRegex(output, r"Warnings: [1-9]\d*")

    def test_course_with_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course_with_duplicate_order(courses_dir, slug="error")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 1)
        self.assertIn("ERROR [duplicate_lesson_order]", output)
        self.assertIn("Courses: 1", output)
        self.assertRegex(output, r"Errors: [1-9]\d*")

    def test_deterministic_course_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_valid_course(courses_dir, slug="z_course")
            _create_valid_course(courses_dir, slug="a_course")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        a_index = output.index("Course: a_course")
        z_index = output.index("Course: z_course")
        self.assertLess(a_index, z_index)


if __name__ == "__main__":
    unittest.main()
