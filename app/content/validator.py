"""Structural validation for course content directories.

This module validates filesystem layout against the Content Engine contract
without reading JSON field values or invoking the runtime scanner.
"""

from pathlib import Path

from app.content.models import ValidationReport


def validate_course(course_dir: Path) -> ValidationReport:
    """Validate the directory structure of a single course.

    Performs structural checks only: directory presence, ``course.json``,
    and lesson subfolders. JSON contents, quiz files, and media assets are
    not validated in this step.

    Args:
        course_dir: Path to the course directory (for example
            ``courses/brands``).

    Returns:
        A :class:`ValidationReport` describing all discovered structural
        issues. The report evaluates to ``False`` when errors are present.
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
    if not course_json_path.is_file():
        report.add_error(
            code="missing_course_json",
            message=f"Required file is missing: {course_json_path.name}",
            path=course_dir,
        )

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
