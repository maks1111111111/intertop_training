"""Cached runtime access to published course content.

``ContentRuntime`` provides cached in-memory access to published courses.
It lazily loads content from the filesystem via ``runtime_loader`` and keeps
a slug index for fast lookups.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.content.runtime_loader import Course, load_published_courses


class ContentRuntime:
    """In-memory cache of published courses for a content base directory."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        self._courses: list[Course] = []
        self._index: dict[str, Course] = {}
        self._loaded = False

    @property
    def base_dir(self) -> Path:
        """Resolved content base directory for this runtime."""
        return self._base_dir

    def get_courses(self) -> list[Course]:
        """Return all published courses, loading from disk on first access."""
        self._ensure_loaded()
        return list(self._courses)

    def get_course(self, slug: str) -> Optional[Course]:
        """Return a published course by slug, or ``None`` if unavailable."""
        self._ensure_loaded()
        return self._index.get(slug)

    def refresh(self) -> None:
        """Reload published courses from disk immediately."""
        self._load()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()

    def _load(self) -> None:
        courses = load_published_courses(self._base_dir)
        self._courses = courses
        self._index = {course.slug: course for course in courses}
        self._loaded = True
