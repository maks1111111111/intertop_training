"""Command-line interface for course content validation and AI import."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from app.ai.bootstrap import create_imported_text_generation_service
from app.content.importer import CourseImporter
from app.content.models import ContentIssue, ValidationReport
from app.content.validator import validate_course

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_COURSES_DIR = _PROJECT_ROOT / "courses"


def _format_path(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def _issue_sort_key(issue: ContentIssue) -> tuple:
    return (
        issue.code,
        issue.message,
        _format_path(issue.path),
        issue.location or "",
    )


def _print_issue(issue: ContentIssue) -> None:
    severity_label = issue.severity.value
    print(f"  {severity_label} [{issue.code}] {issue.message}")
    if issue.path is not None:
        print(f"    path: {_format_path(issue.path)}")
    if issue.location:
        print(f"    location: {issue.location}")


def _print_course_status(report: ValidationReport) -> None:
    summary = report.summary()
    status_label = "READY" if summary["ready"] else "NOT READY"
    print(f"Status: {status_label}")
    print(f"Errors: {summary['errors']}")
    print(f"Warnings: {summary['warnings']}")


def _find_course_dirs(courses_dir: Path) -> list[Path]:
    return sorted(
        (
            entry
            for entry in courses_dir.iterdir()
            if entry.is_dir()
        ),
        key=lambda path: path.name,
    )


def _cmd_validate(argv: Optional[list[str]]) -> int:
    """Validate all course directories and print a human-readable report."""
    parser = argparse.ArgumentParser(
        description="Validate course content in a courses directory.",
    )
    parser.add_argument(
        "courses_dir",
        nargs="?",
        default=str(_DEFAULT_COURSES_DIR),
        help="Path to the courses directory (default: courses/ in project root)",
    )
    args = parser.parse_args(argv)

    courses_dir = Path(args.courses_dir)
    if not courses_dir.exists() or not courses_dir.is_dir():
        print(f"Error: '{courses_dir}' does not exist or is not a directory.")
        return 2

    course_dirs = _find_course_dirs(courses_dir)
    total_errors = 0
    total_warnings = 0

    for course_dir in course_dirs:
        report = validate_course(course_dir)
        errors = sorted(report.errors, key=_issue_sort_key)
        warnings = sorted(report.warnings, key=_issue_sort_key)

        print(f"Course: {course_dir.name}")
        for issue in errors:
            _print_issue(issue)
        for issue in warnings:
            _print_issue(issue)
        _print_course_status(report)
        print()

        course_summary = report.summary()
        total_errors += course_summary["errors"]
        total_warnings += course_summary["warnings"]

    print("Summary:")
    print(f"  Courses: {len(course_dirs)}")
    print(f"  Errors: {total_errors}")
    print(f"  Warnings: {total_warnings}")

    return 1 if total_errors > 0 else 0


def _cmd_generate(argv: Optional[list[str]]) -> int:
    """Generate lessons from an imported document using the AI pipeline."""
    parser = argparse.ArgumentParser(
        description="Generate lessons from an imported document using AI.",
    )
    parser.add_argument(
        "document",
        help="Path to the document to import (pdf, docx, pptx, mp4)",
    )
    args = parser.parse_args(argv)

    document_path = Path(args.document)
    if not document_path.exists() or not document_path.is_file():
        print(f"Error: '{document_path}' does not exist or is not a file.")
        return 2

    importer = CourseImporter()
    text = importer.read_source(document_path)

    generation_service = create_imported_text_generation_service()
    result = generation_service.generate_from_text(text)

    print("Generated lessons:")
    print()
    for index, lesson in enumerate(result.lessons, start=1):
        print(f"{index}. {lesson.title}")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Run the content CLI.

    Validate courses or generate lessons from a document.
    """
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] == "generate":
        return _cmd_generate(args[1:])
    return _cmd_validate(argv)


if __name__ == "__main__":
    raise SystemExit(main())
