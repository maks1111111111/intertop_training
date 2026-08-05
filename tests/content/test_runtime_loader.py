"""Tests for runtime content loading (``app.content.runtime_loader``)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.content.content_pack import ContentPack, build_content_pack
from app.content.runtime_loader import (
    RuntimeContent,
    get_published_course,
    load_published_courses,
    load_runtime_content,
)


def _create_snapshot(root: Path, *, slug: str = "brands") -> tuple[Path, Path]:
    """Create a minimal course directory and snapshot."""
    course_dir = root / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps({"title": "Brands Course", "status": "published", "version": 1}),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "Lesson 1"}),
        encoding="utf-8",
    )

    snapshot_dir = course_dir / ".snapshots" / "v0001"
    snapshot_dir.mkdir(parents=True)
    shutil.copytree(
        course_dir,
        snapshot_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".snapshots"),
    )

    return course_dir, snapshot_dir


def _make_content_pack(
    *,
    course_slug: str = "brands",
    version: int = 1,
    snapshot: str = "/tmp/snapshot",
    files: tuple[str, ...] = ("course.json",),
    files_count: int = 1,
    total_size_bytes: int = 10,
    checksum_sha256: str = "a" * 64,
) -> ContentPack:
    """Build a :class:`ContentPack` with overridable fields for tests."""
    return ContentPack(
        course_slug=course_slug,
        version=version,
        snapshot=snapshot,
        files=files,
        files_count=files_count,
        total_size_bytes=total_size_bytes,
        checksum_sha256=checksum_sha256,
    )


class LoadRuntimeContentTests(unittest.TestCase):
    """Tests for :func:`load_runtime_content`."""

    def test_loads_valid_content_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            content_pack = build_content_pack(course_dir, snapshot_dir, 1)

            runtime = load_runtime_content(content_pack)

            self.assertIsInstance(runtime, RuntimeContent)
            self.assertEqual(runtime.course_slug, "brands")
            self.assertEqual(runtime.version, 1)
            self.assertEqual(runtime.snapshot, snapshot_dir.as_posix())
            self.assertEqual(runtime.files, content_pack.files)
            self.assertEqual(runtime.checksum_sha256, content_pack.checksum_sha256)

    def test_zero_version_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            content_pack = _make_content_pack(
                version=0,
                snapshot=snapshot_dir.as_posix(),
            )

            with self.assertRaises(ValueError):
                load_runtime_content(content_pack)

    def test_empty_checksum_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snapshot_dir = _create_snapshot(Path(tmp))
            content_pack = _make_content_pack(
                snapshot=snapshot_dir.as_posix(),
                checksum_sha256="",
            )

            with self.assertRaises(ValueError):
                load_runtime_content(content_pack)

    def test_mismatched_files_count_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snapshot_dir = _create_snapshot(Path(tmp))
            content_pack = _make_content_pack(
                snapshot=snapshot_dir.as_posix(),
                files=("course.json", "lesson_01/lesson.json"),
                files_count=1,
            )

            with self.assertRaises(ValueError):
                load_runtime_content(content_pack)

    def test_nonexistent_snapshot_raises_value_error(self) -> None:
        content_pack = _make_content_pack(
            snapshot="/nonexistent/snapshot/path",
        )

        with self.assertRaises(ValueError):
            load_runtime_content(content_pack)

    def test_runtime_content_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            content_pack = build_content_pack(course_dir, snapshot_dir, 1)

            runtime = load_runtime_content(content_pack)

            with self.assertRaises(dataclasses.FrozenInstanceError):
                runtime.version = 2  # type: ignore[misc]


def _write_published_course(courses_dir: Path, slug: str = "alpha") -> Path:
    """Create a minimal published course directory."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps({"title": "Alpha Course", "status": "published", "version": 1}),
        encoding="utf-8",
    )

    return course_dir


def _write_lesson(
    course_dir: Path,
    slug: str,
    manifest: dict,
) -> Path:
    """Create a lesson directory with the given manifest."""
    lesson_dir = course_dir / slug
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return lesson_dir


class LessonQualityFieldsLoaderTests(unittest.TestCase):
    """Tests for loading AI lesson quality fields from lesson.json."""

    def test_loads_all_quality_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    "title": "Safety basics",
                    "order": 1,
                    "description": "Main lesson text.",
                    "practical_task": "Inspect the work area before starting.",
                    "checklist": ["Wear PPE", "Check equipment"],
                    "common_mistakes": ["Skipping inspection"],
                    "key_takeaways": ["Safety first"],
                    "application_tips": ["Apply the checklist daily"],
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(len(course.lessons), 1)

        lesson = course.lessons[0]
        self.assertEqual(
            lesson.practical_task,
            "Inspect the work area before starting.",
        )
        self.assertEqual(lesson.checklist, ("Wear PPE", "Check equipment"))
        self.assertEqual(lesson.common_mistakes, ("Skipping inspection",))
        self.assertEqual(lesson.key_takeaways, ("Safety first",))
        self.assertEqual(lesson.application_tips, ("Apply the checklist daily",))
        self.assertIsInstance(lesson.checklist, tuple)
        self.assertIsInstance(lesson.common_mistakes, tuple)
        self.assertIsInstance(lesson.key_takeaways, tuple)
        self.assertIsInstance(lesson.application_tips, tuple)

    def test_legacy_lesson_json_uses_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {"title": "Legacy lesson", "order": 1, "description": "Body"},
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        lesson = course.lessons[0]
        self.assertEqual(lesson.practical_task, "")
        self.assertEqual(lesson.checklist, ())
        self.assertEqual(lesson.common_mistakes, ())
        self.assertEqual(lesson.key_takeaways, ())
        self.assertEqual(lesson.application_tips, ())

    def test_empty_quality_values_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    "title": "Lesson",
                    "order": 1,
                    "description": "Body",
                    "practical_task": "",
                    "checklist": [],
                    "common_mistakes": [],
                    "key_takeaways": [],
                    "application_tips": [],
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        lesson = course.lessons[0]
        self.assertEqual(lesson.practical_task, "")
        self.assertEqual(lesson.checklist, ())
        self.assertEqual(lesson.common_mistakes, ())
        self.assertEqual(lesson.key_takeaways, ())
        self.assertEqual(lesson.application_tips, ())

    def test_invalid_practical_task_type_rejects_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    "title": "Lesson",
                    "order": 1,
                    "description": "Body",
                    "practical_task": 123,
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.lessons, [])

    def test_invalid_string_list_field_rejects_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    "title": "Lesson",
                    "order": 1,
                    "description": "Body",
                    "checklist": "not-a-list",
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.lessons, [])

    def test_non_string_list_item_rejects_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    "title": "Lesson",
                    "order": 1,
                    "description": "Body",
                    "application_tips": ["Valid tip", 123],
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.lessons, [])

    def test_valid_lesson_loads_alongside_invalid_quality_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_broken",
                {
                    "title": "Broken",
                    "order": 1,
                    "description": "Body",
                    "checklist": {"invalid": "object"},
                },
            )
            _write_lesson(
                course_dir,
                "lesson_02",
                {
                    "title": "Valid",
                    "order": 2,
                    "description": "Valid body",
                    "checklist": ["Step one"],
                },
            )

            courses = load_published_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        self.assertEqual(len(courses[0].lessons), 1)
        self.assertEqual(courses[0].lessons[0].path.name, "lesson_02")
        self.assertEqual(courses[0].lessons[0].checklist, ("Step one",))
