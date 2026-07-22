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
class Course:
    slug: str
    title: str
    lessons: list[Lesson]
    cover_path: Optional[Path]


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
