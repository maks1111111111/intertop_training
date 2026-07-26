"""Structural and manifest validation for course content directories.

This module validates filesystem layout and ``course.json`` manifest content
against the Content Engine contract without invoking the runtime scanner.
"""

from pathlib import Path

from app.content.json_loader import load_json_file
from app.content.models import ValidationReport


def _validate_course_manifest(
    course_json_path: Path,
    report: ValidationReport,
) -> None:
    """Validate ``course.json`` root type and required manifest fields.

    Adds errors to ``report`` only; does not mutate JSON data or return a
    separate report.
    """
    errors_before = len(report.errors)

    data = load_json_file(
        course_json_path,
        report,
        missing_code="missing_course_json",
        missing_message=f"Required file is missing: {course_json_path.name}",
    )

    if data is None:
        if len(report.errors) > errors_before:
            return
        report.add_error(
            code="course_json_invalid_type",
            message="Root of course.json must be a JSON object",
            path=course_json_path,
        )
        return

    if not isinstance(data, dict):
        report.add_error(
            code="course_json_invalid_type",
            message="Root of course.json must be a JSON object",
            path=course_json_path,
        )
        return

    # Content Contract v1 defines no mandatory JSON fields in course.json.
    # Optional fields (title, order) are tolerated by the runtime scanner.


def validate_course(course_dir: Path) -> ValidationReport:
    """Validate the directory structure and manifest of a single course.

    Performs structural checks (directory presence, lesson subfolders) and
    validates ``course.json`` contents. ``lesson.json``, ``quiz.json``, and
    media assets are not validated in this step.

    Args:
        course_dir: Path to the course directory (for example
            ``courses/brands``).

    Returns:
        A :class:`ValidationReport` describing all discovered structural
        and manifest issues. The report evaluates to ``False`` when errors
        are present.
    """
    report = ValidationReport()

    if not course_dir.exists():
        report.add_error(
            code="course_directory_not_found",
            message=f"Course directory does not exist: {course_dir}",
            path=course_dir,
        )
        return report

    if not course_dir.is_dir():
        report.add_error(
            code="course_directory_invalid",
            message=f"Course path is not a directory: {course_dir}",
            path=course_dir,
        )
        return report

    course_json_path = course_dir / "course.json"
    _validate_course_manifest(course_json_path, report)

    lesson_dir_count = 0
    for entry in sorted(course_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue

        lesson_dir_count += 1
        lesson_json_path = entry / "lesson.json"
        if not lesson_json_path.is_file():
            report.add_warning(
                code="missing_lesson_json",
                message=(
                    f"Subdirectory is missing required file: "
                    f"{lesson_json_path.name}"
                ),
                path=entry,
                location=entry.name,
            )

    if lesson_dir_count == 0:
        report.add_warning(
            code="course_without_lessons",
            message="Course has no lesson subdirectories",
            path=course_dir,
        )

    return report
