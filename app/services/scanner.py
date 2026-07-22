import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
COURSE_TITLES: dict[str, str] = {
    "mission": "Миссия и ценности компании",
    "service": "Стандарты обслуживания клиентов",
    "brands": "История брендов и технологии",
    "cashier": "Кассовая дисциплина",
}

COURSE_ORDER: list[str] = ["mission", "service", "brands", "cashier"]

SUPPORTED_EXTENSIONS: set[str] = {".mp3", ".mp4"}


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


def _lesson_number(filename: str) -> int:
    prefix = filename.split("_", 1)[0]
    if prefix.isdigit():
        return int(prefix)
    return 9999


def _lesson_title(filename: str) -> str:
    stem = Path(filename).stem
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1].replace("_", " ").strip() or stem
    return stem.replace("_", " ").strip()


def _scan_lessons(course_dir: Path) -> list[Lesson]:
    if not course_dir.is_dir():
        return []

    lessons: list[Lesson] = []

    for lesson_dir in sorted(course_dir.iterdir()):
        if not lesson_dir.is_dir():
            continue

        if not lesson_dir.name.startswith("lesson_"):
            continue

        lesson_json = lesson_dir / "lesson.json"
        if not lesson_json.exists():
            continue

        with lesson_json.open("r", encoding="utf-8") as f:
            data = json.load(f)

        lessons.append(
            Lesson(
                path=lesson_dir,
                number=data["order"],
                title=data["title"],
                description=data["description"],
                image_path=lesson_dir / "image.jpg",
                narration_path=lesson_dir / "narration.mp3",
            )
        )

    lessons.sort(key=lambda lesson: lesson.number)
    return lessons


def _find_cover(covers_dir: Path, slug: str) -> Optional[Path]:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        cover = covers_dir / f"{slug}{ext}"
        if cover.is_file():
            return cover
    return None


def scan_courses(base_dir: Path) -> list[Course]:
    courses_dir = base_dir / "courses"
    covers_dir = base_dir / "covers"

    courses: list[Course] = []
    seen: set[str] = set()

    for slug in COURSE_ORDER:
        course_dir = courses_dir / slug
        if not course_dir.is_dir():
            continue
        seen.add(slug)
        courses.append(
            Course(
                slug=slug,
                title=COURSE_TITLES.get(slug, slug),
                lessons=_scan_lessons(course_dir),
                cover_path=_find_cover(covers_dir, slug),
            )
        )

    if courses_dir.is_dir():
        for course_dir in sorted(courses_dir.iterdir()):
            if not course_dir.is_dir():
                continue
            slug = course_dir.name
            if slug in seen:
                continue
            courses.append(
                Course(
                    slug=slug,
                    title=COURSE_TITLES.get(slug, slug.replace("_", " ").title()),
                    lessons=_scan_lessons(course_dir),
                    cover_path=_find_cover(covers_dir, slug),
                )
            )

    return courses


def get_course(base_dir: Path, slug: str) -> Optional[Course]:
    for course in scan_courses(base_dir):
        if course.slug == slug:
            return course
    return None
