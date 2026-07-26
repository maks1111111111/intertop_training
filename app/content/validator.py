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


def _validate_lesson_manifest(
    lesson_json_path: Path,
    report: ValidationReport,
    *,
    location: str,
) -> None:
    """Validate ``lesson.json`` root type and optional manifest fields.

    Adds errors to ``report`` only; does not mutate JSON data or return a
    separate report.
    """
    errors_before = len(report.errors)

    data = load_json_file(
        lesson_json_path,
        report,
        location=location,
    )

    if data is None:
        if len(report.errors) > errors_before:
            return
        report.add_error(
            code="lesson_json_invalid_type",
            message="Root of lesson.json must be a JSON object",
            path=lesson_json_path,
            location=location,
        )
        return

    if not isinstance(data, dict):
        report.add_error(
            code="lesson_json_invalid_type",
            message="Root of lesson.json must be a JSON object",
            path=lesson_json_path,
            location=location,
        )
        return

    if "title" in data and not isinstance(data["title"], str):
        report.add_error(
            code="lesson_title_invalid_type",
            message="Field title must be a string",
            path=lesson_json_path,
            location=f"{location}.title",
        )

    if "description" in data and not isinstance(data["description"], str):
        report.add_error(
            code="lesson_description_invalid_type",
            message="Field description must be a string",
            path=lesson_json_path,
            location=f"{location}.description",
        )

    if "order" in data:
        order_value = data["order"]
        if isinstance(order_value, bool) or not isinstance(order_value, int):
            report.add_error(
                code="lesson_order_invalid_type",
                message="Field order must be an integer",
                path=lesson_json_path,
                location=f"{location}.order",
            )


def _validate_quiz_manifest(
    quiz_json_path: Path,
    report: ValidationReport,
    *,
    location: str,
) -> None:
    """Validate ``quiz.json`` root type and top-level manifest fields.

    Adds errors to ``report`` only; does not mutate JSON data or return a
    separate report. Individual questions are not validated in this step.
    """
    if not quiz_json_path.is_file():
        return

    errors_before = len(report.errors)

    data = load_json_file(
        quiz_json_path,
        report,
        location=location,
    )

    if data is None:
        if len(report.errors) > errors_before:
            return
        report.add_error(
            code="quiz_json_invalid_type",
            message="Root of quiz.json must be a JSON object",
            path=quiz_json_path,
            location=location,
        )
        return

    if not isinstance(data, dict):
        report.add_error(
            code="quiz_json_invalid_type",
            message="Root of quiz.json must be a JSON object",
            path=quiz_json_path,
            location=location,
        )
        return

    if "questions" not in data:
        report.add_error(
            code="quiz_questions_missing",
            message="Required field 'questions' is missing",
            path=quiz_json_path,
            location=f"{location}.questions",
        )
    elif not isinstance(data["questions"], list):
        report.add_error(
            code="quiz_questions_invalid_type",
            message="Field 'questions' must be an array",
            path=quiz_json_path,
            location=f"{location}.questions",
        )
    elif len(data["questions"]) == 0:
        report.add_error(
            code="quiz_questions_empty",
            message="Field 'questions' must contain at least one question",
            path=quiz_json_path,
            location=f"{location}.questions",
        )

    if "id" in data:
        if not isinstance(data["id"], str):
            report.add_error(
                code="quiz_id_invalid_type",
                message="Field 'id' must be a string",
                path=quiz_json_path,
                location=f"{location}.id",
            )
        elif not data["id"].strip():
            report.add_error(
                code="quiz_id_empty",
                message="Field 'id' must not be empty",
                path=quiz_json_path,
                location=f"{location}.id",
            )

    if "title" in data:
        if not isinstance(data["title"], str):
            report.add_error(
                code="quiz_title_invalid_type",
                message="Field 'title' must be a string",
                path=quiz_json_path,
                location=f"{location}.title",
            )
        elif not data["title"].strip():
            report.add_error(
                code="quiz_title_empty",
                message="Field 'title' must not be empty",
                path=quiz_json_path,
                location=f"{location}.title",
            )

    if "passing_score" in data:
        passing_score = data["passing_score"]
        if isinstance(passing_score, bool) or not isinstance(passing_score, int):
            report.add_error(
                code="quiz_passing_score_invalid_type",
                message="Field 'passing_score' must be an integer",
                path=quiz_json_path,
                location=f"{location}.passing_score",
            )
        elif passing_score < 1 or passing_score > 100:
            report.add_error(
                code="quiz_passing_score_out_of_range",
                message="Field 'passing_score' must be between 1 and 100",
                path=quiz_json_path,
                location=f"{location}.passing_score",
            )

    if "version" in data:
        version = data["version"]
        if isinstance(version, bool) or not isinstance(version, int):
            report.add_error(
                code="quiz_version_invalid_type",
                message="Field 'version' must be an integer",
                path=quiz_json_path,
                location=f"{location}.version",
            )

    if "randomize_questions" in data and not isinstance(
        data["randomize_questions"], bool
    ):
        report.add_error(
            code="quiz_randomize_questions_invalid_type",
            message="Field 'randomize_questions' must be a boolean",
            path=quiz_json_path,
            location=f"{location}.randomize_questions",
        )

    if "randomize_options" in data and not isinstance(
        data["randomize_options"], bool
    ):
        report.add_error(
            code="quiz_randomize_options_invalid_type",
            message="Field 'randomize_options' must be a boolean",
            path=quiz_json_path,
            location=f"{location}.randomize_options",
        )


def validate_course(course_dir: Path) -> ValidationReport:
    """Validate the directory structure and manifest of a single course.

    Performs structural checks (directory presence, lesson subfolders),
    validates ``course.json`` contents, validates ``lesson.json`` when
    present, and validates top-level ``quiz.json`` fields when the file
    exists. Quiz questions and media assets are not validated in this step.

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
        else:
            _validate_lesson_manifest(
                lesson_json_path,
                report,
                location=entry.name,
            )

    if lesson_dir_count == 0:
        report.add_warning(
            code="course_without_lessons",
            message="Course has no lesson subdirectories",
            path=course_dir,
        )

    quiz_json_path = course_dir / "quiz.json"
    _validate_quiz_manifest(quiz_json_path, report, location="quiz")

    return report
