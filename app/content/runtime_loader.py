"""Runtime loader for published Content Engine content.

Loads course content from the filesystem and validated content packs into
immutable runtime views without duplicating parsing logic elsewhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.content.content_pack import ContentPack
from app.content.contract import (
    COURSE_COVER_FILENAMES,
    COURSE_JSON_FILENAME,
    LESSON_IMAGE_FILENAMES,
    LESSON_JSON_FILENAME,
    LESSON_NARRATION_FILENAMES,
    QUIZ_JSON_FILENAME,
)
from app.content.practical_task import PracticalTask

_PUBLISHED_STATUS = "published"
_COURSE_STATUSES = frozenset({"draft", "published", "archived"})


@dataclass(frozen=True)
class Lesson:
    path: Path
    number: int
    title: str
    description: str
    image_path: Optional[Path]
    narration_path: Optional[Path]
    practical_task: str = ""
    structured_practical_task: Optional[PracticalTask] = None
    checklist: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
    key_takeaways: tuple[str, ...] = ()
    application_tips: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuizOption:
    id: str
    text: str


@dataclass(frozen=True)
class QuizQuestion:
    id: str
    question_type: str
    text: str
    options: list[QuizOption]
    correct_option_ids: list[str]
    explanation: str
    lesson: str
    difficulty: int
    tags: list[str]
    ai_context: str


@dataclass(frozen=True)
class Quiz:
    id: str
    title: str
    passing_score: int
    questions: list[QuizQuestion]
    version: int
    randomize_questions: bool
    randomize_options: bool


@dataclass(frozen=True)
class Course:
    slug: str
    title: str
    status: str
    version: int
    lessons: list[Lesson]
    cover_path: Optional[Path]
    quiz: Optional[Quiz]
    description: str = ""
    language: str = ""


@dataclass(frozen=True)
class RuntimeContent:
    """Immutable runtime view of a published course content pack.

    The loader trusts a previously built :class:`ContentPack` after validating
    its internal consistency and snapshot availability. It does not rescan the
    snapshot directory or recompute checksums.
    """

    course_slug: str
    version: int
    snapshot: str
    files: tuple[str, ...]
    checksum_sha256: str


def _parse_course_status(metadata: dict) -> str:
    if "status" not in metadata:
        return _PUBLISHED_STATUS

    raw_status = metadata["status"]
    if isinstance(raw_status, str) and raw_status in _COURSE_STATUSES:
        return raw_status

    return ""


def _parse_course_language(metadata: dict) -> str:
    if "language" not in metadata:
        return ""

    raw_language = metadata["language"]
    if not isinstance(raw_language, str):
        return ""

    return raw_language.strip()


def _parse_course_description(metadata: dict) -> str:
    if "description" not in metadata:
        return ""

    raw_description = metadata["description"]
    if not isinstance(raw_description, str):
        return ""

    return raw_description


def _parse_course_version(metadata: dict) -> int:
    if "version" not in metadata:
        return 1

    raw_version = metadata["version"]
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        return 1

    if raw_version < 1:
        return 1

    return raw_version


def _read_json_object(path: Path) -> Optional[dict]:
    """Read a JSON file and return its root object, or ``None`` on failure."""
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return data


def _find_file(directory: Path, filenames: tuple[str, ...]) -> Optional[Path]:
    for filename in filenames:
        path = directory / filename

        if path.is_file():
            return path

    return None


def _parse_lesson_string_field(
    metadata: dict,
    field_name: str,
    *,
    default: str = "",
) -> Optional[str]:
    """Return a lesson string field value, or ``None`` when the type is invalid."""
    if field_name not in metadata:
        return default

    value = metadata[field_name]
    if not isinstance(value, str):
        return None

    return value


def _parse_lesson_string_tuple_field(
    metadata: dict,
    field_name: str,
) -> Optional[tuple[str, ...]]:
    """Return a tuple of strings from a lesson list field, or ``None`` on failure."""
    if field_name not in metadata:
        return ()

    value = metadata[field_name]
    if not isinstance(value, list):
        return None

    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        items.append(item)

    return tuple(items)


def _parse_structured_practical_task(
    metadata: dict,
) -> tuple[Optional[PracticalTask], bool]:
    """Parse ``structured_practical_task`` from lesson metadata.

    Returns:
        A pair ``(task, ok)``. When ``ok`` is ``False``, the lesson is
        invalid. When ``ok`` is ``True``, ``task`` is ``None`` if the field
        is absent or JSON ``null``, otherwise a parsed :class:`PracticalTask`.
    """
    if "structured_practical_task" not in metadata:
        return None, True

    raw = metadata["structured_practical_task"]
    if raw is None:
        return None, True

    if not isinstance(raw, dict):
        return None, False

    if "title" not in raw:
        return None, False
    title = raw["title"]
    if not isinstance(title, str):
        return None, False

    if "description" not in raw:
        return None, False
    description = raw["description"]
    if not isinstance(description, str):
        return None, False

    if "expected_result" not in raw:
        return None, False
    expected_result = raw["expected_result"]
    if not isinstance(expected_result, str):
        return None, False

    if "estimated_minutes" in raw:
        estimated_minutes_raw = raw["estimated_minutes"]
        if estimated_minutes_raw is None:
            estimated_minutes = None
        elif isinstance(estimated_minutes_raw, bool):
            return None, False
        elif isinstance(estimated_minutes_raw, int):
            estimated_minutes = estimated_minutes_raw
        else:
            return None, False
    else:
        estimated_minutes = None

    return (
        PracticalTask(
            title=title,
            description=description,
            expected_result=expected_result,
            estimated_minutes=estimated_minutes,
        ),
        True,
    )


def _load_lesson(lesson_dir: Path) -> Optional[Lesson]:
    metadata_path = lesson_dir / LESSON_JSON_FILENAME

    if not metadata_path.is_file():
        return None

    metadata = _read_json_object(metadata_path)
    if metadata is None:
        return None

    title = str(metadata.get("title") or lesson_dir.name)
    description = str(metadata.get("description") or "")

    practical_task = _parse_lesson_string_field(metadata, "practical_task")
    if practical_task is None:
        return None

    checklist = _parse_lesson_string_tuple_field(metadata, "checklist")
    if checklist is None:
        return None

    common_mistakes = _parse_lesson_string_tuple_field(metadata, "common_mistakes")
    if common_mistakes is None:
        return None

    key_takeaways = _parse_lesson_string_tuple_field(metadata, "key_takeaways")
    if key_takeaways is None:
        return None

    application_tips = _parse_lesson_string_tuple_field(metadata, "application_tips")
    if application_tips is None:
        return None

    structured_practical_task, structured_ok = _parse_structured_practical_task(
        metadata
    )
    if not structured_ok:
        return None

    try:
        number = int(metadata.get("order", 9999))
    except (TypeError, ValueError):
        number = 9999

    image_path = _find_file(lesson_dir, LESSON_IMAGE_FILENAMES)

    narration_path = _find_file(lesson_dir, LESSON_NARRATION_FILENAMES)

    return Lesson(
        path=lesson_dir,
        number=number,
        title=title,
        description=description,
        image_path=image_path,
        narration_path=narration_path,
        practical_task=practical_task,
        structured_practical_task=structured_practical_task,
        checklist=checklist,
        common_mistakes=common_mistakes,
        key_takeaways=key_takeaways,
        application_tips=application_tips,
    )


def _parse_quiz_option(raw_option: object) -> Optional[QuizOption]:
    if not isinstance(raw_option, dict):
        return None

    option_id_raw = raw_option.get("id")
    if not isinstance(option_id_raw, str):
        return None
    option_id = option_id_raw.strip()
    if not option_id:
        return None

    option_text_raw = raw_option.get("text")
    if not isinstance(option_text_raw, str):
        return None
    option_text = option_text_raw.strip()
    if not option_text:
        return None

    return QuizOption(id=option_id, text=option_text)


def _parse_quiz_question(raw_question: object) -> Optional[QuizQuestion]:
    if not isinstance(raw_question, dict):
        return None

    if raw_question.get("type") != "single_choice":
        return None

    question_id_raw = raw_question.get("id")
    if not isinstance(question_id_raw, str):
        return None
    question_id = question_id_raw.strip()
    if not question_id:
        return None

    question_text_raw = raw_question.get("text")
    if not isinstance(question_text_raw, str):
        return None
    question_text = question_text_raw.strip()
    if not question_text:
        return None

    raw_options = raw_question.get("options")
    if not isinstance(raw_options, list):
        return None

    options: list[QuizOption] = []
    option_ids: set[str] = set()

    for raw_option in raw_options:
        option = _parse_quiz_option(raw_option)
        if option is None:
            return None

        if option.id in option_ids:
            return None

        option_ids.add(option.id)
        options.append(option)

    if len(options) < 2:
        return None

    raw_correct_option_ids = raw_question.get("correct_option_ids")
    if (
        not isinstance(raw_correct_option_ids, list)
        or len(raw_correct_option_ids) != 1
    ):
        return None

    correct_option_id_raw = raw_correct_option_ids[0]
    if not isinstance(correct_option_id_raw, str):
        return None
    correct_option_id = correct_option_id_raw.strip()
    if not correct_option_id:
        return None

    if correct_option_id not in option_ids:
        return None

    explanation = raw_question.get("explanation")
    if not isinstance(explanation, str):
        explanation = ""
    else:
        explanation = explanation.strip()

    lesson_raw = raw_question.get("lesson", "")
    if isinstance(lesson_raw, str):
        lesson = lesson_raw.strip()
    else:
        lesson = ""

    try:
        difficulty = int(raw_question.get("difficulty", 1))
    except (TypeError, ValueError):
        difficulty = 1

    raw_tags = raw_question.get("tags", [])
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if isinstance(tag, str):
                tag_text = tag.strip()
                if tag_text:
                    tags.append(tag_text)

    ai_context_raw = raw_question.get("ai_context", "")
    if isinstance(ai_context_raw, str):
        ai_context = ai_context_raw.strip()
    else:
        ai_context = ""

    return QuizQuestion(
        id=question_id,
        question_type="single_choice",
        text=question_text,
        options=options,
        correct_option_ids=[correct_option_id],
        explanation=explanation,
        lesson=lesson,
        difficulty=difficulty,
        tags=tags,
        ai_context=ai_context,
    )


def _load_quiz(course_dir: Path) -> Optional[Quiz]:
    quiz_path = course_dir / QUIZ_JSON_FILENAME

    if not quiz_path.is_file():
        return None

    data = _read_json_object(quiz_path)
    if data is None:
        return None

    course_slug = course_dir.name

    quiz_id_raw = data.get("id")
    if isinstance(quiz_id_raw, str):
        quiz_id = quiz_id_raw.strip()
    else:
        quiz_id = ""

    if not quiz_id:
        quiz_id = f"{course_slug}_quiz"

    title_raw = data.get("title")
    if isinstance(title_raw, str):
        title = title_raw.strip()
    else:
        title = ""

    if not title:
        title = "Итоговый тест"

    try:
        passing_score = int(data.get("passing_score", 80))
    except (TypeError, ValueError):
        passing_score = 80

    if passing_score < 1 or passing_score > 100:
        passing_score = 80

    try:
        version = int(data.get("version", 1))
    except (TypeError, ValueError):
        version = 1

    randomize_questions_raw = data.get("randomize_questions", True)
    if isinstance(randomize_questions_raw, bool):
        randomize_questions = randomize_questions_raw
    else:
        randomize_questions = True

    randomize_options_raw = data.get("randomize_options", True)
    if isinstance(randomize_options_raw, bool):
        randomize_options = randomize_options_raw
    else:
        randomize_options = True

    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        return None

    questions: list[QuizQuestion] = []
    seen_question_ids: set[str] = set()

    for raw_question in raw_questions:
        question = _parse_quiz_question(raw_question)
        if question is None:
            return None

        if question.id in seen_question_ids:
            return None

        seen_question_ids.add(question.id)
        questions.append(question)

    return Quiz(
        id=quiz_id,
        title=title,
        passing_score=passing_score,
        questions=questions,
        version=version,
        randomize_questions=randomize_questions,
        randomize_options=randomize_options,
    )


def _list_course_directories(base_dir: Path) -> list[Path]:
    """Return immediate child directories of ``base_dir``, or ``[]`` on failure."""
    try:
        return [entry for entry in base_dir.iterdir() if entry.is_dir()]
    except OSError:
        return []


def _load_course_from_directory(course_dir: Path) -> Optional[tuple[int, Course]]:
    metadata_path = course_dir / COURSE_JSON_FILENAME

    if not metadata_path.is_file():
        return None

    metadata = _read_json_object(metadata_path)
    if metadata is None:
        return None

    title = str(metadata.get("title") or course_dir.name)

    try:
        order = int(metadata.get("order", 9999))
    except (TypeError, ValueError):
        order = 9999

    lessons: list[Lesson] = []

    for lesson_dir in course_dir.iterdir():
        if not lesson_dir.is_dir():
            continue

        lesson = _load_lesson(lesson_dir)

        if lesson is not None:
            lessons.append(lesson)

    lessons.sort(key=lambda lesson: (lesson.number, lesson.path.name))

    cover_path = _find_file(course_dir, COURSE_COVER_FILENAMES)

    course = Course(
        slug=course_dir.name,
        title=title,
        status=_parse_course_status(metadata),
        version=_parse_course_version(metadata),
        lessons=lessons,
        cover_path=cover_path,
        quiz=_load_quiz(course_dir),
        description=_parse_course_description(metadata),
        language=_parse_course_language(metadata),
    )

    return order, course


def _load_sorted_courses(base_dir: Path) -> list[Course]:
    """Load valid courses from ``base_dir`` regardless of publication status."""
    if not base_dir.is_dir():
        return []

    loaded_courses: list[tuple[int, Course]] = []

    for course_dir in _list_course_directories(base_dir):
        try:
            loaded_course = _load_course_from_directory(course_dir)
        except OSError:
            continue

        if loaded_course is not None:
            loaded_courses.append(loaded_course)

    loaded_courses.sort(key=lambda item: (item[0], item[1].slug))
    return [course for _, course in loaded_courses]


def load_courses(base_dir: Path) -> list[Course]:
    """Load valid courses from ``base_dir`` regardless of publication status."""
    return _load_sorted_courses(base_dir)


def get_course(base_dir: Path, slug: str) -> Optional[Course]:
    """Return one course by slug regardless of publication status."""
    normalized_slug = str(slug or "").strip()
    if not normalized_slug:
        return None

    for course in load_courses(base_dir):
        if course.slug == normalized_slug:
            return course

    return None


def load_published_courses(base_dir: Path) -> list[Course]:
    """Load all published courses from ``base_dir``.

    Each course directory is loaded independently. A malformed course is
    skipped without preventing other courses from loading.
    """
    return [
        course
        for course in _load_sorted_courses(base_dir)
        if course.status == _PUBLISHED_STATUS
    ]


def get_published_course(base_dir: Path, slug: str) -> Optional[Course]:
    """Return a published course by slug, or ``None`` if unavailable."""
    course = get_course(base_dir, slug)
    if course is None or course.status != _PUBLISHED_STATUS:
        return None
    return course


def _validate_content_pack_version(version: int) -> None:
    """Ensure ``version`` is a positive integer (bool is not accepted)."""
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"Version must be a positive integer, got {version!r}")
    if version < 1:
        raise ValueError(f"Version must be at least 1, got {version}")


def _validate_files_count(files_count: int, files: tuple[str, ...]) -> None:
    """Ensure ``files_count`` matches the number of listed files."""
    if files_count != len(files):
        raise ValueError(
            "files_count does not match len(files): "
            f"files_count={files_count}, len(files)={len(files)}"
        )


def _validate_checksum_sha256(checksum_sha256: str) -> None:
    """Ensure ``checksum_sha256`` is a non-empty string."""
    if not isinstance(checksum_sha256, str):
        raise ValueError(
            "checksum_sha256 must be a string, "
            f"got {type(checksum_sha256).__name__}"
        )
    if not checksum_sha256:
        raise ValueError("checksum_sha256 must not be empty")


def _validate_snapshot(snapshot: str) -> None:
    """Ensure ``snapshot`` points to an existing directory."""
    if not isinstance(snapshot, str):
        raise ValueError(
            f"snapshot must be a string, got {type(snapshot).__name__}"
        )
    if not snapshot:
        raise ValueError("snapshot must not be empty")

    snapshot_path = Path(snapshot)
    if not snapshot_path.exists():
        raise ValueError(f"Snapshot directory does not exist: {snapshot}")
    if not snapshot_path.is_dir():
        raise ValueError(f"Snapshot path is not a directory: {snapshot}")


def _validate_content_pack(content_pack: ContentPack) -> None:
    """Validate a :class:`ContentPack` before runtime loading."""
    _validate_content_pack_version(content_pack.version)
    _validate_files_count(content_pack.files_count, content_pack.files)
    _validate_checksum_sha256(content_pack.checksum_sha256)
    _validate_snapshot(content_pack.snapshot)


def load_runtime_content(content_pack: ContentPack) -> RuntimeContent:
    """Load a validated runtime view from a :class:`ContentPack`.

    The function checks internal consistency of ``content_pack`` and verifies
    that the referenced snapshot directory exists. It does not rescan the
    snapshot, recompute checksums, or read course files such as ``lesson.json``.

    Args:
        content_pack: A previously built content pack description.

    Returns:
        An immutable :class:`RuntimeContent` ready for runtime use.

    Raises:
        ValueError: If ``content_pack`` is inconsistent or its snapshot is
            unavailable.
    """
    _validate_content_pack(content_pack)

    return RuntimeContent(
        course_slug=content_pack.course_slug,
        version=content_pack.version,
        snapshot=content_pack.snapshot,
        files=content_pack.files,
        checksum_sha256=content_pack.checksum_sha256,
    )
