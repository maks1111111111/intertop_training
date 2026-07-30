"""Public facade for runtime course loading.

Delegates filesystem scanning to :mod:`app.content.runtime_loader` while
preserving the historical import path for handlers and services.
"""

from pathlib import Path
from typing import Optional

from app.content.runtime_loader import (
    Course,
    Lesson,
    Quiz,
    QuizOption,
    QuizQuestion,
    get_published_course,
    load_published_courses,
)

__all__ = [
    "Course",
    "Lesson",
    "Quiz",
    "QuizOption",
    "QuizQuestion",
    "get_course",
    "scan_courses",
]


def scan_courses(base_dir: Path) -> list[Course]:
    return load_published_courses(base_dir)


def get_course(base_dir: Path, slug: str) -> Optional[Course]:
    return get_published_course(base_dir, slug)
