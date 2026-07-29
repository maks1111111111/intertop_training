"""Tests for course manifest validation in the Content Validator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.content.models import ValidationReport
from app.content.validator import validate_course


def _create_course_dir(
    courses_dir: Path,
    slug: str = "test",
    *,
    course_manifest: Optional[dict] = None,
    with_lesson: bool = True,
    with_lesson_json: bool = True,
) -> Path:
    """Create a minimal course directory for validator tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    manifest = course_manifest if course_manifest is not None else {}
    (course_dir / "course.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    if with_lesson:
        lesson_dir = course_dir / "lesson_01"
        lesson_dir.mkdir()
        if with_lesson_json:
            (lesson_dir / "lesson.json").write_text("{}", encoding="utf-8")

    return course_dir


def _status_errors(report):
    """Return status-related errors from a validation report."""
    return [
        issue
        for issue in report.errors
        if issue.code in {"course_status_invalid_type", "invalid_course_status"}
    ]


def _version_errors(report):
    """Return version-related errors from a validation report."""
    return [
        issue
        for issue in report.errors
        if issue.code in {"course_version_invalid_type", "invalid_course_version"}
    ]


def _publication_errors(report):
    """Return publication-specific errors from a validation report."""
    return [
        issue
        for issue in report.errors
        if issue.code in {
            "published_course_without_lessons",
            "published_lesson_manifest_missing",
        }
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


class CourseVersionValidationTests(unittest.TestCase):
    """Validation of optional ``version`` field in ``course.json``."""

    def test_missing_version_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            report = validate_course(course_dir)

        self.assertEqual(_version_errors(report), [])

    def test_version_one_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"version": 1},
            )
            report = validate_course(course_dir)

        self.assertEqual(_version_errors(report), [])

    def test_version_two_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"version": 2},
            )
            report = validate_course(course_dir)

        self.assertEqual(_version_errors(report), [])

    def test_version_fifteen_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"version": 15},
            )
            report = validate_course(course_dir)

        self.assertEqual(_version_errors(report), [])

    def test_version_zero_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"version": 0},
            )
            report = validate_course(course_dir)

        version_errors = _version_errors(report)
        self.assertEqual(len(version_errors), 1)
        issue = version_errors[0]
        self.assertEqual(issue.code, "invalid_course_version")
        self.assertEqual(issue.path, course_dir / "course.json")
        self.assertEqual(issue.location, "version")

    def test_version_negative_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"version": -1},
            )
            report = validate_course(course_dir)

        version_errors = _version_errors(report)
        self.assertEqual(len(version_errors), 1)
        issue = version_errors[0]
        self.assertEqual(issue.code, "invalid_course_version")
        self.assertEqual(issue.path, course_dir / "course.json")
        self.assertEqual(issue.location, "version")

    def test_non_integer_version_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"version": "2"},
            )
            report = validate_course(course_dir)

        version_errors = _version_errors(report)
        self.assertEqual(len(version_errors), 1)
        issue = version_errors[0]
        self.assertEqual(issue.code, "course_version_invalid_type")
        self.assertEqual(issue.path, course_dir / "course.json")
        self.assertEqual(issue.location, "version")


class PublishedCourseValidationTests(unittest.TestCase):
    """Publication-specific validation for explicitly published courses."""

    def test_published_course_without_lessons_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "published"},
                with_lesson=False,
            )
            report = validate_course(course_dir)

        errors = _publication_errors(report)
        self.assertEqual(len(errors), 1)
        issue = errors[0]
        self.assertEqual(issue.code, "published_course_without_lessons")
        self.assertEqual(issue.path, course_dir)
        self.assertEqual(issue.location, "status")

    def test_draft_course_without_lessons_has_no_publication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft"},
                with_lesson=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_archived_course_without_lessons_has_no_publication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "archived"},
                with_lesson=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_course_without_status_and_without_lessons_has_no_publication_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                with_lesson=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_published_lesson_without_manifest_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "published"},
                with_lesson_json=False,
            )
            report = validate_course(course_dir)

        errors = _publication_errors(report)
        self.assertEqual(len(errors), 1)
        issue = errors[0]
        self.assertEqual(issue.code, "published_lesson_manifest_missing")
        self.assertEqual(issue.path, course_dir / "lesson_01")
        self.assertEqual(issue.location, "lesson_01")

    def test_draft_lesson_without_manifest_has_no_publication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft"},
                with_lesson_json=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_archived_lesson_without_manifest_has_no_publication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "archived"},
                with_lesson_json=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_course_without_status_and_lesson_without_manifest_has_no_publication_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                with_lesson_json=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_valid_published_course_has_no_publication_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "published"},
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_invalid_status_does_not_trigger_publication_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "active"},
                with_lesson=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])

    def test_invalid_status_type_does_not_trigger_publication_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": 123},
                with_lesson=False,
            )
            report = validate_course(course_dir)

        self.assertEqual(_publication_errors(report), [])


class ValidationReportReleaseTests(unittest.TestCase):
    """Release readiness helpers on :class:`ValidationReport`."""

    def test_empty_report_is_release_ready(self) -> None:
        report = ValidationReport()

        self.assertTrue(report.is_release_ready())
        self.assertTrue(bool(report))

    def test_warnings_only_is_release_ready(self) -> None:
        report = ValidationReport()
        report.add_warning("sample_warning", "Advisory issue")

        self.assertTrue(report.is_release_ready())
        self.assertTrue(bool(report))

    def test_error_is_not_release_ready(self) -> None:
        report = ValidationReport()
        report.add_error("sample_error", "Blocking issue")

        self.assertFalse(report.is_release_ready())
        self.assertFalse(bool(report))

    def test_summary_empty_report(self) -> None:
        report = ValidationReport()

        self.assertEqual(
            report.summary(),
            {"ready": True, "errors": 0, "warnings": 0},
        )

    def test_summary_with_warnings_only(self) -> None:
        report = ValidationReport()
        report.add_warning("sample_warning", "Advisory issue")

        self.assertEqual(
            report.summary(),
            {"ready": True, "errors": 0, "warnings": 1},
        )

    def test_summary_with_errors(self) -> None:
        report = ValidationReport()
        report.add_error("sample_error", "Blocking issue")
        report.add_warning("sample_warning", "Advisory issue")

        self.assertEqual(
            report.summary(),
            {"ready": False, "errors": 1, "warnings": 1},
        )

    def test_release_gate_empty_report(self) -> None:
        report = ValidationReport()

        self.assertEqual(
            report.release_gate(),
            {"allowed": True, "ready": True, "errors": 0, "warnings": 0},
        )

    def test_release_gate_with_warnings_only(self) -> None:
        report = ValidationReport()
        report.add_warning("sample_warning", "Advisory issue")

        self.assertEqual(
            report.release_gate(),
            {"allowed": True, "ready": True, "errors": 0, "warnings": 1},
        )

    def test_release_gate_with_errors(self) -> None:
        report = ValidationReport()
        report.add_error("sample_error", "Blocking issue")
        report.add_warning("sample_warning", "Advisory issue")

        self.assertEqual(
            report.release_gate(),
            {"allowed": False, "ready": False, "errors": 1, "warnings": 1},
        )


if __name__ == "__main__":
    unittest.main()
