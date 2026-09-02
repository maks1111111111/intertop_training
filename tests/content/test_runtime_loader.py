"""Tests for runtime content loading (``app.content.runtime_loader``)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.content.content_pack import ContentPack, build_content_pack
from app.content.practical_task import PracticalTask
from app.content.runtime_loader import (
    RuntimeContent,
    get_course,
    get_published_course,
    load_courses,
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


class StructuredPracticalTaskLoaderTests(unittest.TestCase):
    """Tests for loading structured_practical_task from lesson.json."""

    def _base_manifest(self) -> dict:
        return {
            "title": "Safety basics",
            "order": 1,
            "description": "Main lesson text.",
        }

    def test_loads_full_structured_practical_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    **self._base_manifest(),
                    "structured_practical_task": {
                        "title": "Проверка рабочего места",
                        "description": "Осмотрите рабочую зону перед началом смены.",
                        "expected_result": "Все риски обнаружены и устранены.",
                        "estimated_minutes": 10,
                    },
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        task = course.lessons[0].structured_practical_task
        self.assertIsInstance(task, PracticalTask)
        assert task is not None
        self.assertEqual(task.title, "Проверка рабочего места")
        self.assertEqual(
            task.description,
            "Осмотрите рабочую зону перед началом смены.",
        )
        self.assertEqual(
            task.expected_result,
            "Все риски обнаружены и устранены.",
        )
        self.assertEqual(task.estimated_minutes, 10)

    def test_missing_key_yields_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(course_dir, "lesson_01", self._base_manifest())

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.lessons[0].structured_practical_task)

    def test_explicit_null_yields_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    **self._base_manifest(),
                    "structured_practical_task": None,
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.lessons[0].structured_practical_task)

    def test_missing_estimated_minutes_yields_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    **self._base_manifest(),
                    "structured_practical_task": {
                        "title": "Task",
                        "description": "Do the task.",
                        "expected_result": "Done.",
                    },
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        task = course.lessons[0].structured_practical_task
        assert task is not None
        self.assertIsNone(task.estimated_minutes)

    def test_null_estimated_minutes_yields_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    **self._base_manifest(),
                    "structured_practical_task": {
                        "title": "Task",
                        "description": "Do the task.",
                        "expected_result": "Done.",
                        "estimated_minutes": None,
                    },
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        task = course.lessons[0].structured_practical_task
        assert task is not None
        self.assertIsNone(task.estimated_minutes)

    def test_legacy_and_structured_fields_load_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    **self._base_manifest(),
                    "practical_task": "Legacy task",
                    "structured_practical_task": {
                        "title": "Structured task",
                        "description": "Structured description.",
                        "expected_result": "Structured result.",
                        "estimated_minutes": 5,
                    },
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        lesson = course.lessons[0]
        self.assertEqual(lesson.practical_task, "Legacy task")
        task = lesson.structured_practical_task
        assert task is not None
        self.assertEqual(task.title, "Structured task")
        self.assertEqual(task.description, "Structured description.")
        self.assertEqual(task.expected_result, "Structured result.")
        self.assertEqual(task.estimated_minutes, 5)

    def test_invalid_root_type_rejects_lesson(self) -> None:
        invalid_roots = ("string", ["list"], 123)
        for invalid_root in invalid_roots:
            with self.subTest(invalid_root=invalid_root):
                with tempfile.TemporaryDirectory() as tmp:
                    courses_dir = Path(tmp)
                    course_dir = _write_published_course(courses_dir)
                    _write_lesson(
                        course_dir,
                        "lesson_01",
                        {
                            **self._base_manifest(),
                            "structured_practical_task": invalid_root,
                        },
                    )

                    course = get_published_course(courses_dir, "alpha")

                self.assertIsNotNone(course)
                assert course is not None
                self.assertEqual(course.lessons, [])

    def test_missing_required_fields_reject_lesson(self) -> None:
        base_task = {
            "title": "Task",
            "description": "Description.",
            "expected_result": "Result.",
        }
        missing_fields = ("title", "description", "expected_result")
        for field in missing_fields:
            with self.subTest(missing_field=field):
                task = {key: value for key, value in base_task.items() if key != field}
                with tempfile.TemporaryDirectory() as tmp:
                    courses_dir = Path(tmp)
                    course_dir = _write_published_course(courses_dir)
                    _write_lesson(
                        course_dir,
                        "lesson_01",
                        {
                            **self._base_manifest(),
                            "structured_practical_task": task,
                        },
                    )

                    course = get_published_course(courses_dir, "alpha")

                self.assertIsNotNone(course)
                assert course is not None
                self.assertEqual(course.lessons, [])

    def test_non_string_required_fields_reject_lesson(self) -> None:
        base_task = {
            "title": "Task",
            "description": "Description.",
            "expected_result": "Result.",
        }
        for field in ("title", "description", "expected_result"):
            with self.subTest(field=field):
                task = dict(base_task)
                task[field] = 123
                with tempfile.TemporaryDirectory() as tmp:
                    courses_dir = Path(tmp)
                    course_dir = _write_published_course(courses_dir)
                    _write_lesson(
                        course_dir,
                        "lesson_01",
                        {
                            **self._base_manifest(),
                            "structured_practical_task": task,
                        },
                    )

                    course = get_published_course(courses_dir, "alpha")

                self.assertIsNotNone(course)
                assert course is not None
                self.assertEqual(course.lessons, [])

    def test_invalid_estimated_minutes_type_rejects_lesson(self) -> None:
        base_task = {
            "title": "Task",
            "description": "Description.",
            "expected_result": "Result.",
        }
        invalid_values = ("15", 3.5, True)
        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                task = dict(base_task)
                task["estimated_minutes"] = invalid_value
                with tempfile.TemporaryDirectory() as tmp:
                    courses_dir = Path(tmp)
                    course_dir = _write_published_course(courses_dir)
                    _write_lesson(
                        course_dir,
                        "lesson_01",
                        {
                            **self._base_manifest(),
                            "structured_practical_task": task,
                        },
                    )

                    course = get_published_course(courses_dir, "alpha")

                self.assertIsNotNone(course)
                assert course is not None
                self.assertEqual(course.lessons, [])

    def test_extra_fields_do_not_break_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_published_course(courses_dir)
            _write_lesson(
                course_dir,
                "lesson_01",
                {
                    **self._base_manifest(),
                    "structured_practical_task": {
                        "title": "Task",
                        "description": "Description.",
                        "expected_result": "Result.",
                        "notes": "ignored",
                    },
                },
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        task = course.lessons[0].structured_practical_task
        assert task is not None
        self.assertEqual(task.title, "Task")


class CourseDescriptionLoaderTests(unittest.TestCase):
    """Tests for loading course description from course.json."""

    def test_loads_description_from_course_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = courses_dir / "alpha"
            course_dir.mkdir()
            (course_dir / "course.json").write_text(
                json.dumps(
                    {
                        "title": "Alpha Course",
                        "description": "Retail training overview.",
                        "status": "published",
                    }
                ),
                encoding="utf-8",
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.description, "Retail training overview.")

    def test_missing_description_defaults_to_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_published_course(courses_dir)

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.description, "")

    def test_non_string_description_defaults_to_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = courses_dir / "alpha"
            course_dir.mkdir()
            (course_dir / "course.json").write_text(
                json.dumps(
                    {
                        "title": "Alpha Course",
                        "description": 123,
                        "status": "published",
                    }
                ),
                encoding="utf-8",
            )

            course = get_published_course(courses_dir, "alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.description, "")


def _write_course_with_status(
    courses_dir: Path,
    slug: str,
    *,
    status: str,
    title: str = "Sample Course",
) -> Path:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps({"title": title, "status": status, "version": 1}),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "Lesson 1", "order": 1, "description": "Body"}),
        encoding="utf-8",
    )
    return course_dir


class AllStatusLoaderTests(unittest.TestCase):
    """Tests for all-status course loading helpers."""

    def test_load_courses_returns_published_and_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course_with_status(courses_dir, "published", status="published")
            _write_course_with_status(courses_dir, "archived", status="archived")

            courses = load_courses(courses_dir)

        self.assertEqual([course.slug for course in courses], ["archived", "published"])

    def test_load_published_courses_excludes_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course_with_status(courses_dir, "published", status="published")
            _write_course_with_status(courses_dir, "archived", status="archived")

            courses = load_published_courses(courses_dir)

        self.assertEqual([course.slug for course in courses], ["published"])

    def test_get_course_returns_archived_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course_with_status(
                courses_dir,
                "archived",
                status="archived",
                title="Archived Course",
            )

            course = get_course(courses_dir, "archived")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.status, "archived")
        self.assertEqual(course.title, "Archived Course")

    def test_get_published_course_excludes_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course_with_status(courses_dir, "archived", status="archived")

            course = get_published_course(courses_dir, "archived")

        self.assertIsNone(course)


if __name__ == "__main__":
    unittest.main()
