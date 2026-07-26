import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Lesson:
    path: Path
    number: int
    title: str
    description: str
    image_path: Optional[Path]
    narration_path: Optional[Path]


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
    lessons: list[Lesson]
    cover_path: Optional[Path]
    quiz: Optional[Quiz]


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def _find_file(directory: Path, filenames: tuple[str, ...]) -> Optional[Path]:
    for filename in filenames:
        path = directory / filename

        if path.is_file():
            return path

    return None


def _scan_lesson(lesson_dir: Path) -> Optional[Lesson]:
    metadata_path = lesson_dir / "lesson.json"

    if not metadata_path.is_file():
        return None

    metadata = _read_json(metadata_path)

    title = str(metadata.get("title") or lesson_dir.name)
    description = str(metadata.get("description") or "")

    try:
        number = int(metadata.get("order", 9999))
    except (TypeError, ValueError):
        number = 9999

    image_path = _find_file(
        lesson_dir,
        ("image.jpg", "image.jpeg", "image.png", "image.webp"),
    )

    narration_path = _find_file(
        lesson_dir,
        ("narration.mp3", "narration.m4a", "narration.wav", "narration.ogg"),
    )

    return Lesson(
        path=lesson_dir,
        number=number,
        title=title,
        description=description,
        image_path=image_path,
        narration_path=narration_path,
    )


def _scan_quiz(course_dir: Path) -> Optional[Quiz]:
    quiz_path = course_dir / "quiz.json"

    if not quiz_path.is_file():
        return None

    data = _read_json(quiz_path)

    if not data:
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
    if not isinstance(raw_questions, list):
        return None

    questions: list[QuizQuestion] = []
    seen_question_ids: set[str] = set()

    for raw_question in raw_questions:
        if not isinstance(raw_question, dict):
            continue

        if raw_question.get("type") != "single_choice":
            continue

        question_id_raw = raw_question.get("id")
        if not isinstance(question_id_raw, str):
            continue
        question_id = question_id_raw.strip()
        if not question_id:
            continue

        if question_id in seen_question_ids:
            continue

        question_text_raw = raw_question.get("text")
        if not isinstance(question_text_raw, str):
            continue
        question_text = question_text_raw.strip()
        if not question_text:
            continue

        raw_options = raw_question.get("options")
        if not isinstance(raw_options, list):
            continue

        options: list[QuizOption] = []
        option_ids: set[str] = set()
        duplicate_option_id = False

        for raw_option in raw_options:
            if not isinstance(raw_option, dict):
                continue

            option_id_raw = raw_option.get("id")
            if not isinstance(option_id_raw, str):
                continue
            option_id = option_id_raw.strip()
            if not option_id:
                continue

            if option_id in option_ids:
                duplicate_option_id = True
                break

            option_text_raw = raw_option.get("text")
            if not isinstance(option_text_raw, str):
                continue
            option_text = option_text_raw.strip()
            if not option_text:
                continue

            option_ids.add(option_id)
            options.append(QuizOption(id=option_id, text=option_text))

        if duplicate_option_id:
            continue

        if len(options) < 2:
            continue

        raw_correct_option_ids = raw_question.get("correct_option_ids")
        if (
            not isinstance(raw_correct_option_ids, list)
            or len(raw_correct_option_ids) != 1
        ):
            continue

        correct_option_id_raw = raw_correct_option_ids[0]
        if not isinstance(correct_option_id_raw, str):
            continue
        correct_option_id = correct_option_id_raw.strip()
        if not correct_option_id:
            continue

        if correct_option_id not in option_ids:
            continue

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

        seen_question_ids.add(question_id)
        questions.append(
            QuizQuestion(
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
        )

    if not questions:
        return None

    return Quiz(
        id=quiz_id,
        title=title,
        passing_score=passing_score,
        questions=questions,
        version=version,
        randomize_questions=randomize_questions,
        randomize_options=randomize_options,
    )


def _scan_course(course_dir: Path) -> Optional[tuple[int, Course]]:
    metadata_path = course_dir / "course.json"

    if not metadata_path.is_file():
        return None

    metadata = _read_json(metadata_path)

    title = str(metadata.get("title") or course_dir.name)

    try:
        order = int(metadata.get("order", 9999))
    except (TypeError, ValueError):
        order = 9999

    lessons: list[Lesson] = []

    for lesson_dir in course_dir.iterdir():
        if not lesson_dir.is_dir():
            continue

        lesson = _scan_lesson(lesson_dir)

        if lesson is not None:
            lessons.append(lesson)

    lessons.sort(key=lambda lesson: (lesson.number, lesson.path.name))

    cover_path = _find_file(
        course_dir,
        ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp"),
    )

    course = Course(
        slug=course_dir.name,
        title=title,
        lessons=lessons,
        cover_path=cover_path,
        quiz=_scan_quiz(course_dir),
    )

    return order, course


def scan_courses(base_dir: Path) -> list[Course]:
    if not base_dir.is_dir():
        return []

    scanned_courses: list[tuple[int, Course]] = []

    for course_dir in base_dir.iterdir():
        if not course_dir.is_dir():
            continue

        scanned_course = _scan_course(course_dir)

        if scanned_course is not None:
            scanned_courses.append(scanned_course)

    scanned_courses.sort(key=lambda item: (item[0], item[1].slug))

    return [course for _, course in scanned_courses]


def get_course(base_dir: Path, slug: str) -> Optional[Course]:
    for course in scan_courses(base_dir):
        if course.slug == slug:
            return course

    return None
