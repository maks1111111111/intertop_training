"""Command-line interface for validating course content directories."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from app.content.models import ContentIssue
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


def _find_course_dirs(courses_dir: Path) -> list[Path]:
    return sorted(
        (
            entry
            for entry in courses_dir.iterdir()
            if entry.is_dir()
        ),
        key=lambda path: path.name,
    )


def main(argv: Optional[list[str]] = None) -> int:
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
        if not errors and not warnings:
            print("  OK")
        else:
            for issue in errors:
                _print_issue(issue)
            for issue in warnings:
                _print_issue(issue)
        print()

        total_errors += len(errors)
        total_warnings += len(warnings)

    print("Summary:")
    print(f"  Courses: {len(course_dirs)}")
    print(f"  Errors: {total_errors}")
    print(f"  Warnings: {total_warnings}")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
