"""Content quality validation for the Intertop Training Content Engine.

This module hosts rules that go beyond structural and manifest validation:
readability, completeness, pedagogical quality, and similar advisory checks.
Quality rules are added incrementally here without changing structural
validators or the runtime scanner.
"""

from pathlib import Path

from app.content.contract import COURSE_JSON_FILENAME
from app.content.json_loader import load_json_file
from app.content.models import ValidationReport


def _check_text_quality(
    text: str,
    report: ValidationReport,
    *,
    path: Path,
    location: str,
) -> None:
    """Check a text field for common whitespace and formatting issues.

    Adds advisory warnings to ``report`` for leading or trailing spaces,
    double spaces, and three or more consecutive blank lines.
    """
    if text.startswith(" "):
        report.add_warning(
            code="text_leading_whitespace",
            message="Field has leading whitespace",
            path=path,
            location=location,
        )

    if text.endswith(" "):
        report.add_warning(
            code="text_trailing_whitespace",
            message="Field has trailing whitespace",
            path=path,
            location=location,
        )

    if "  " in text:
        report.add_warning(
            code="text_double_spaces",
            message="Field contains double spaces",
            path=path,
            location=location,
        )

    consecutive_blank_lines = 0
    for line in text.split("\n"):
        if line.strip() == "":
            consecutive_blank_lines += 1
            if consecutive_blank_lines >= 3:
                report.add_warning(
                    code="text_excessive_blank_lines",
                    message=(
                        "Field contains three or more consecutive blank lines"
                    ),
                    path=path,
                    location=location,
                )
                break
        else:
            consecutive_blank_lines = 0


def _check_min_text_length(
    text: str,
    minimum: int,
    report: ValidationReport,
    *,
    path: Path,
    location: str,
    field_label: str,
) -> None:
    """Check that a text field meets a minimum length after stripping.

    Adds an advisory warning when ``text.strip()`` is shorter than
    ``minimum`` characters.
    """
    if len(text.strip()) < minimum:
        report.add_warning(
            code="text_too_short",
            message=(
                f"{field_label} is too short: expected at least "
                f"{minimum} characters"
            ),
            path=path,
            location=location,
        )


def _validate_course_quality(
    course_dir: Path,
    report: ValidationReport,
) -> None:
    """Run course-level quality rules.

    Checks optional ``title`` and ``description`` fields in ``course.json``.
    """
    course_json_path = course_dir / COURSE_JSON_FILENAME
    if not course_json_path.is_file():
        return

    data = load_json_file(course_json_path, report)
    if not isinstance(data, dict):
        return

    title = data.get("title")
    if isinstance(title, str):
        _check_text_quality(
            title,
            report,
            path=course_json_path,
            location="title",
        )
        _check_min_text_length(
            title,
            5,
            report,
            path=course_json_path,
            location="title",
            field_label="Course title",
        )

    description = data.get("description")
    if isinstance(description, str):
        _check_text_quality(
            description,
            report,
            path=course_json_path,
            location="description",
        )
        _check_min_text_length(
            description,
            30,
            report,
            path=course_json_path,
            location="description",
            field_label="Course description",
        )


def _validate_lesson_quality(
    lesson_dir: Path,
    report: ValidationReport,
    *,
    location: str,
) -> None:
    """Run lesson-level quality rules.

    Placeholder for future rules such as description length, media presence,
    or narration alignment checks.
    """
    pass


def _validate_question_quality(
    raw_question: dict,
    quiz_json_path: Path,
    report: ValidationReport,
    *,
    location: str,
) -> None:
    """Run question-level quality rules.

    Placeholder for future rules such as explanation quality, difficulty
    consistency, or tag completeness checks.
    """
    pass


def validate_quality(
    course_dir: Path,
    report: ValidationReport,
) -> None:
    """Validate content quality beyond structural and manifest checks.

    Adds findings to ``report`` only. This entry point orchestrates
    course-, lesson-, and question-level quality rules once implemented.
    Structural issues are expected to be reported earlier by
    :func:`validate_course`.

    Args:
        course_dir: Path to the course directory (for example
            ``courses/brands``).
        report: Shared validation report to append quality findings to.
    """
    _validate_course_quality(course_dir, report)
