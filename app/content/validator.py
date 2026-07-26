"""Structural and manifest validation for course content directories.

This module validates filesystem layout and ``course.json`` manifest content
against the Content Engine contract without invoking the runtime scanner.
"""

from pathlib import Path
from typing import AbstractSet, Optional

from app.content.contract import (
    COURSE_COVER_EXTENSIONS,
    COURSE_COVER_STEM,
    COURSE_JSON_FILENAME,
    LESSON_IMAGE_EXTENSIONS,
    LESSON_IMAGE_STEM,
    LESSON_JSON_FILENAME,
    LESSON_NARRATION_EXTENSIONS,
    LESSON_NARRATION_STEM,
    QUIZ_JSON_FILENAME,
)
from app.content.json_loader import load_json_file
from app.content.models import ValidationReport
from app.content.quality import validate_quality


def _validate_media_slot(
    directory: Path,
    stem: str,
    allowed_extensions: AbstractSet[str],
    slot_name: str,
    report: ValidationReport,
    *,
    path: Optional[Path] = None,
    location: Optional[str] = None,
    multiple_files_code: str,
    unsupported_format_code: str,
) -> None:
    """Validate a single optional media file slot against allowed extensions.

    Scans ``directory`` for files whose stem matches ``stem``, reports
    unsupported extensions and multiple supported matches.
    """
    if not directory.is_dir():
        return

    error_path = path or directory
    supported_files: list[Path] = []

    for entry in directory.iterdir():
        if not entry.is_file() or entry.stem != stem:
            continue

        extension = entry.suffix.lower()
        if extension in allowed_extensions:
            supported_files.append(entry)
            continue

        report.add_error(
            code=unsupported_format_code,
            message=f"Unsupported {slot_name} format",
            path=entry,
            location=location,
        )

    if len(supported_files) > 1:
        report.add_error(
            code=multiple_files_code,
            message=f"Multiple {slot_name} files found",
            path=error_path,
            location=location,
        )


def _validate_course_cover(
    course_dir: Path,
    report: ValidationReport,
) -> None:
    """Validate optional course cover media files."""
    _validate_media_slot(
        course_dir,
        COURSE_COVER_STEM,
        COURSE_COVER_EXTENSIONS,
        "course cover",
        report,
        path=course_dir,
        multiple_files_code="course_cover_multiple_files",
        unsupported_format_code="course_cover_unsupported_format",
    )


def _validate_lesson_media(
    lesson_dir: Path,
    report: ValidationReport,
    *,
    location: str,
) -> None:
    """Validate optional lesson image and narration media files."""
    _validate_media_slot(
        lesson_dir,
        LESSON_IMAGE_STEM,
        LESSON_IMAGE_EXTENSIONS,
        "lesson image",
        report,
        path=lesson_dir,
        location=location,
        multiple_files_code="lesson_image_multiple_files",
        unsupported_format_code="lesson_image_unsupported_format",
    )
    _validate_media_slot(
        lesson_dir,
        LESSON_NARRATION_STEM,
        LESSON_NARRATION_EXTENSIONS,
        "narration",
        report,
        path=lesson_dir,
        location=location,
        multiple_files_code="lesson_narration_multiple_files",
        unsupported_format_code="lesson_narration_unsupported_format",
    )


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
    lesson_slugs: set[str],
) -> None:
    """Validate ``quiz.json`` root type and top-level manifest fields.

    Adds errors to ``report`` only; does not mutate JSON data or return a
    separate report. Question contents are validated when ``questions`` is a
    non-empty array.
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

    questions = data.get("questions")
    if isinstance(questions, list) and len(questions) > 0:
        _validate_quiz_questions(
            questions,
            quiz_json_path,
            report,
            location=location,
            lesson_slugs=lesson_slugs,
        )


def _validate_quiz_questions(
    questions: list,
    quiz_json_path: Path,
    report: ValidationReport,
    *,
    location: str,
    lesson_slugs: set[str],
) -> None:
    """Validate each question in the quiz ``questions`` array.

    Adds errors to ``report`` only; does not mutate JSON data or return a
    separate report.
    """
    seen_question_ids: set[str] = set()

    for index, raw_question in enumerate(questions):
        question_location = f"{location}.questions[{index}]"

        if not isinstance(raw_question, dict):
            report.add_error(
                code="quiz_question_invalid_type",
                message="Question must be a JSON object",
                path=quiz_json_path,
                location=question_location,
            )
            continue

        if "type" not in raw_question:
            report.add_error(
                code="quiz_question_type_missing",
                message="Required field 'type' is missing",
                path=quiz_json_path,
                location=f"{question_location}.type",
            )
        elif not isinstance(raw_question["type"], str):
            report.add_error(
                code="quiz_question_type_invalid_type",
                message="Field 'type' must be a string",
                path=quiz_json_path,
                location=f"{question_location}.type",
            )
        elif raw_question["type"] != "single_choice":
            report.add_error(
                code="quiz_question_type_unsupported",
                message="Field 'type' must be 'single_choice'",
                path=quiz_json_path,
                location=f"{question_location}.type",
            )

        if "id" not in raw_question:
            report.add_error(
                code="quiz_question_id_missing",
                message="Required field 'id' is missing",
                path=quiz_json_path,
                location=f"{question_location}.id",
            )
        elif not isinstance(raw_question["id"], str):
            report.add_error(
                code="quiz_question_id_invalid_type",
                message="Field 'id' must be a string",
                path=quiz_json_path,
                location=f"{question_location}.id",
            )
        elif not raw_question["id"].strip():
            report.add_error(
                code="quiz_question_id_empty",
                message="Field 'id' must not be empty",
                path=quiz_json_path,
                location=f"{question_location}.id",
            )
        else:
            question_id = raw_question["id"].strip()
            if question_id in seen_question_ids:
                report.add_error(
                    code="quiz_question_duplicate_id",
                    message="Question id must be unique within the quiz",
                    path=quiz_json_path,
                    location=f"{question_location}.id",
                )
            else:
                seen_question_ids.add(question_id)

        if "text" not in raw_question:
            report.add_error(
                code="quiz_question_text_missing",
                message="Required field 'text' is missing",
                path=quiz_json_path,
                location=f"{question_location}.text",
            )
        elif not isinstance(raw_question["text"], str):
            report.add_error(
                code="quiz_question_text_invalid_type",
                message="Field 'text' must be a string",
                path=quiz_json_path,
                location=f"{question_location}.text",
            )
        elif not raw_question["text"].strip():
            report.add_error(
                code="quiz_question_text_empty",
                message="Field 'text' must not be empty",
                path=quiz_json_path,
                location=f"{question_location}.text",
            )

        valid_option_ids: set[str] = set()
        duplicate_option_id = False
        valid_options_count = 0

        if "options" not in raw_question:
            report.add_error(
                code="quiz_question_options_missing",
                message="Required field 'options' is missing",
                path=quiz_json_path,
                location=f"{question_location}.options",
            )
        elif not isinstance(raw_question["options"], list):
            report.add_error(
                code="quiz_question_options_invalid_type",
                message="Field 'options' must be an array",
                path=quiz_json_path,
                location=f"{question_location}.options",
            )
        else:
            for option_index, raw_option in enumerate(raw_question["options"]):
                option_location = f"{question_location}.options[{option_index}]"

                if not isinstance(raw_option, dict):
                    report.add_error(
                        code="quiz_option_invalid_type",
                        message="Option must be a JSON object",
                        path=quiz_json_path,
                        location=option_location,
                    )
                    continue

                option_id: Optional[str] = None

                if "id" not in raw_option:
                    report.add_error(
                        code="quiz_option_id_missing",
                        message="Required field 'id' is missing",
                        path=quiz_json_path,
                        location=f"{option_location}.id",
                    )
                elif not isinstance(raw_option["id"], str):
                    report.add_error(
                        code="quiz_option_id_invalid_type",
                        message="Field 'id' must be a string",
                        path=quiz_json_path,
                        location=f"{option_location}.id",
                    )
                elif not raw_option["id"].strip():
                    report.add_error(
                        code="quiz_option_id_empty",
                        message="Field 'id' must not be empty",
                        path=quiz_json_path,
                        location=f"{option_location}.id",
                    )
                else:
                    option_id = raw_option["id"].strip()
                    if option_id in valid_option_ids:
                        duplicate_option_id = True
                        report.add_error(
                            code="quiz_option_duplicate_id",
                            message="Option id must be unique within the question",
                            path=quiz_json_path,
                            location=f"{option_location}.id",
                        )

                if "text" not in raw_option:
                    report.add_error(
                        code="quiz_option_text_missing",
                        message="Required field 'text' is missing",
                        path=quiz_json_path,
                        location=f"{option_location}.text",
                    )
                elif not isinstance(raw_option["text"], str):
                    report.add_error(
                        code="quiz_option_text_invalid_type",
                        message="Field 'text' must be a string",
                        path=quiz_json_path,
                        location=f"{option_location}.text",
                    )
                elif not raw_option["text"].strip():
                    report.add_error(
                        code="quiz_option_text_empty",
                        message="Field 'text' must not be empty",
                        path=quiz_json_path,
                        location=f"{option_location}.text",
                    )
                elif option_id is not None and option_id not in valid_option_ids:
                    valid_option_ids.add(option_id)
                    valid_options_count += 1

            if not duplicate_option_id and valid_options_count < 2:
                report.add_error(
                    code="quiz_question_not_enough_options",
                    message="Question must have at least two valid options",
                    path=quiz_json_path,
                    location=f"{question_location}.options",
                )

        if "correct_option_ids" not in raw_question:
            report.add_error(
                code="quiz_correct_option_ids_missing",
                message="Required field 'correct_option_ids' is missing",
                path=quiz_json_path,
                location=f"{question_location}.correct_option_ids",
            )
        elif not isinstance(raw_question["correct_option_ids"], list):
            report.add_error(
                code="quiz_correct_option_ids_invalid_type",
                message="Field 'correct_option_ids' must be an array",
                path=quiz_json_path,
                location=f"{question_location}.correct_option_ids",
            )
        else:
            correct_option_ids = raw_question["correct_option_ids"]
            if len(correct_option_ids) != 1:
                report.add_error(
                    code="quiz_correct_option_ids_invalid_count",
                    message=(
                        "Field 'correct_option_ids' must contain exactly one id"
                    ),
                    path=quiz_json_path,
                    location=f"{question_location}.correct_option_ids",
                )
            else:
                correct_option_id_raw = correct_option_ids[0]
                if not isinstance(correct_option_id_raw, str):
                    report.add_error(
                        code="quiz_correct_option_id_empty",
                        message="Correct option id must not be empty",
                        path=quiz_json_path,
                        location=f"{question_location}.correct_option_ids[0]",
                    )
                elif not correct_option_id_raw.strip():
                    report.add_error(
                        code="quiz_correct_option_id_empty",
                        message="Correct option id must not be empty",
                        path=quiz_json_path,
                        location=f"{question_location}.correct_option_ids[0]",
                    )
                elif correct_option_id_raw.strip() not in valid_option_ids:
                    report.add_error(
                        code="quiz_correct_option_id_unknown",
                        message="Correct option id must reference a valid option",
                        path=quiz_json_path,
                        location=f"{question_location}.correct_option_ids[0]",
                    )

        if "explanation" in raw_question and not isinstance(
            raw_question["explanation"], str
        ):
            report.add_error(
                code="quiz_question_explanation_invalid_type",
                message="Field 'explanation' must be a string",
                path=quiz_json_path,
                location=f"{question_location}.explanation",
            )

        if "lesson" in raw_question:
            if not isinstance(raw_question["lesson"], str):
                report.add_error(
                    code="quiz_question_lesson_invalid_type",
                    message="Field 'lesson' must be a string",
                    path=quiz_json_path,
                    location=f"{question_location}.lesson",
                )
            else:
                lesson_ref = raw_question["lesson"].strip()
                if lesson_ref and lesson_ref not in lesson_slugs:
                    report.add_error(
                        code="quiz_question_lesson_unknown",
                        message=(
                            "Field 'lesson' must reference an existing lesson slug"
                        ),
                        path=quiz_json_path,
                        location=f"{question_location}.lesson",
                    )

        if "difficulty" in raw_question:
            difficulty = raw_question["difficulty"]
            if isinstance(difficulty, bool) or not isinstance(difficulty, int):
                report.add_error(
                    code="quiz_question_difficulty_invalid_type",
                    message="Field 'difficulty' must be an integer",
                    path=quiz_json_path,
                    location=f"{question_location}.difficulty",
                )

        if "tags" in raw_question:
            tags = raw_question["tags"]
            if not isinstance(tags, list):
                report.add_error(
                    code="quiz_question_tags_invalid_type",
                    message="Field 'tags' must be an array",
                    path=quiz_json_path,
                    location=f"{question_location}.tags",
                )
            else:
                for tag_index, tag in enumerate(tags):
                    if not isinstance(tag, str):
                        report.add_error(
                            code="quiz_question_tag_invalid_type",
                            message="Tag must be a string",
                            path=quiz_json_path,
                            location=f"{question_location}.tags[{tag_index}]",
                        )

        if "ai_context" in raw_question and not isinstance(
            raw_question["ai_context"], str
        ):
            report.add_error(
                code="quiz_question_ai_context_invalid_type",
                message="Field 'ai_context' must be a string",
                path=quiz_json_path,
                location=f"{question_location}.ai_context",
            )


def validate_course(course_dir: Path) -> ValidationReport:
    """Validate the directory structure and manifest of a single course.

    Performs structural checks (directory presence, lesson subfolders),
    validates ``course.json`` contents, validates ``lesson.json`` when
    present, and validates ``quiz.json`` including question contents when the
    file exists, and validates optional media assets for course cover and
    lesson image/narration slots.

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

    course_json_path = course_dir / COURSE_JSON_FILENAME
    _validate_course_manifest(course_json_path, report)
    _validate_course_cover(course_dir, report)

    lesson_dir_count = 0
    lesson_slugs: set[str] = set()
    for entry in sorted(course_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue

        lesson_dir_count += 1
        lesson_json_path = entry / LESSON_JSON_FILENAME
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
            lesson_slugs.add(entry.name)
            _validate_lesson_manifest(
                lesson_json_path,
                report,
                location=entry.name,
            )

        _validate_lesson_media(entry, report, location=entry.name)

    if lesson_dir_count == 0:
        report.add_warning(
            code="course_without_lessons",
            message="Course has no lesson subdirectories",
            path=course_dir,
        )

    quiz_json_path = course_dir / QUIZ_JSON_FILENAME
    _validate_quiz_manifest(
        quiz_json_path,
        report,
        location="quiz",
        lesson_slugs=lesson_slugs,
    )

    validate_quality(course_dir, report)

    return report
