"""Content quality validation for the Intertop Training Content Engine.

This module hosts rules that go beyond structural and manifest validation:
readability, completeness, pedagogical quality, and similar advisory checks.
Quality rules are added incrementally here without changing structural
validators or the runtime scanner.
"""

from pathlib import Path

from app.content.models import ValidationReport


def _validate_course_quality(
    course_dir: Path,
    report: ValidationReport,
) -> None:
    """Run course-level quality rules.

    Placeholder for future rules such as title length, metadata completeness,
    or cover asset recommendations.
    """
    pass


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

    Currently a no-op placeholder that preserves the extension point without
    duplicating content loading or changing validation behavior.

    Args:
        course_dir: Path to the course directory (for example
            ``courses/brands``).
        report: Shared validation report to append quality findings to.
    """
    del course_dir, report
