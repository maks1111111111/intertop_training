"""Tests for cached runtime access (``app.content.runtime``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content.runtime import ContentRuntime
from app.content.runtime_loader import load_published_courses


def _write_minimal_course(
    courses_dir: Path,
    slug: str,
    *,
    course_order: int = 1,
    status: str = "published",
) -> Path:
    """Create a minimal valid published course directory."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "status": status,
                "order": course_order,
                "version": 1,
            }
        ),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "First lesson", "order": 1}),
        encoding="utf-8",
    )

    return course_dir


class ContentRuntimeTests(unittest.TestCase):
    """Tests for :class:`ContentRuntime`."""

    def test_first_load_reads_filesystem_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                first = runtime.get_courses()
                second = runtime.get_courses()

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].slug, "alpha")
        self.assertEqual(second, first)
        loader.assert_called_once()

    def test_repeated_calls_use_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_course("alpha")
                runtime.get_course("alpha")
                runtime.get_courses()

        loader.assert_called_once()

    def test_refresh_reloads_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                runtime.refresh()

        self.assertEqual(loader.call_count, 2)

    def test_after_refresh_get_courses_does_not_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                runtime.refresh()
                runtime.get_courses()

        self.assertEqual(loader.call_count, 2)

    def test_get_course_uses_slug_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course = runtime.get_course("alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "alpha")
        loader.assert_called_once()

    def test_missing_slug_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            course = runtime.get_course("missing")

        self.assertIsNone(course)

    def test_empty_directory_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                first = runtime.get_courses()
                second = runtime.get_courses()

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        loader.assert_called_once()

    def test_refresh_picks_up_new_courses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            self.assertEqual(runtime.get_courses(), [])

            _write_minimal_course(courses_dir, "new_course")
            runtime.refresh()

            courses = runtime.get_courses()

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "new_course")

    def test_after_refresh_new_course_available_via_get_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            self.assertIsNone(runtime.get_course("new_course"))

            _write_minimal_course(courses_dir, "new_course")
            runtime.refresh()

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course = runtime.get_course("new_course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "new_course")
        loader.assert_not_called()

    def test_independent_instances_for_same_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            first = ContentRuntime(courses_dir)
            second = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                first.get_courses()
                second.get_courses()

        self.assertEqual(loader.call_count, 2)
        self.assertIsNot(first, second)

    def test_refresh_updates_list_and_index_consistently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            _write_minimal_course(courses_dir, "beta", course_order=2)
            runtime.refresh()

            courses = runtime.get_courses()
            slugs = {course.slug for course in courses}

        self.assertEqual(slugs, {"alpha", "beta"})
        self.assertIsNotNone(runtime.get_course("alpha"))
        self.assertIsNotNone(runtime.get_course("beta"))
        self.assertIsNone(runtime.get_course("missing"))


if __name__ == "__main__":
    unittest.main()
