"""Cached runtime access to published course content.

``ContentRuntime`` provides cached in-memory access to published courses.
It lazily loads content from the filesystem via ``runtime_loader`` and keeps
a slug index for fast lookups. Content is reloaded automatically when the
on-disk course tree changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.content.runtime_loader import Course, load_published_courses

_SCAN_ERROR_FINGERPRINT = (("__scan_error__",),)


def _content_fingerprint(base_dir: Path) -> tuple:
    """Build a deterministic metadata fingerprint for *base_dir* contents.

    Each filesystem entry contributes its relative path, kind, and for files
    ``st_mtime_ns`` and ``st_size``. The result is sorted by relative path so
    comparisons are stable regardless of directory iteration order.

    ``FileNotFoundError`` and ``OSError`` during traversal are recorded in the
    fingerprint so the next access retries loading instead of serving stale
    cache entries after a concurrent write.
    """
    if not base_dir.is_dir():
        return ()

    entries: list[tuple] = []

    try:
        paths = sorted(base_dir.rglob("*"), key=lambda item: item.as_posix())
    except OSError:
        return _SCAN_ERROR_FINGERPRINT

    for path in paths:
        try:
            relative = path.relative_to(base_dir).as_posix()
            if path.is_dir():
                entries.append((relative, "dir"))
                continue
            if path.is_file():
                stat_result = path.stat()
                entries.append(
                    (
                        relative,
                        "file",
                        stat_result.st_mtime_ns,
                        stat_result.st_size,
                    )
                )
                continue
            entries.append((relative, "other"))
        except (FileNotFoundError, OSError):
            try:
                relative = path.relative_to(base_dir).as_posix()
            except ValueError:
                relative = path.as_posix()
            entries.append((relative, "missing"))

    return tuple(entries)


class ContentRuntime:
    """In-memory cache of published courses for a content base directory."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        self._courses: list[Course] = []
        self._index: dict[str, Course] = {}
        self._loaded = False
        self._fingerprint: Optional[tuple] = None

    @property
    def base_dir(self) -> Path:
        """Resolved content base directory for this runtime."""
        return self._base_dir

    def get_courses(self) -> list[Course]:
        """Return all published courses, loading from disk on first access."""
        self._ensure_fresh()
        return list(self._courses)

    def get_course(self, slug: str) -> Optional[Course]:
        """Return a published course by slug, or ``None`` if unavailable."""
        self._ensure_fresh()
        return self._index.get(slug)

    def refresh(self) -> None:
        """Reload published courses from disk immediately."""
        self._load()

    def cached_courses_count(self) -> int:
        """Return the number of courses currently held in the cache.

        Performs an initial load if the runtime has never been loaded.
        Unlike :meth:`get_courses`, this method does not check the filesystem
        fingerprint and does not trigger automatic reloads. It is intended
        for refresh lifecycle statistics that need the cached state before
        and after an explicit :meth:`refresh` call.
        """
        if not self._loaded:
            self._load()
        return len(self._courses)

    def _ensure_fresh(self) -> None:
        if not self._loaded:
            self._load()
            return

        current_fingerprint = _content_fingerprint(self._base_dir)
        if (
            current_fingerprint == _SCAN_ERROR_FINGERPRINT
            or current_fingerprint != self._fingerprint
        ):
            self._load()

    def _load(self) -> None:
        courses = load_published_courses(self._base_dir)
        self._courses = courses
        self._index = {course.slug: course for course in courses}
        self._loaded = True
        self._fingerprint = _content_fingerprint(self._base_dir)

