"""Tests for course snapshots (``app.content.snapshots``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content.snapshots import SNAPSHOTS_DIR_NAME, create_snapshot


def _create_course_dir(
    courses_dir: Path,
    slug: str = "service",
) -> Path:
    """Create a minimal course directory for snapshot tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps({"title": "Service Course", "status": "published", "version": 1}),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "Lesson 1"}),
        encoding="utf-8",
    )

    return course_dir


class CreateSnapshotTests(unittest.TestCase):
    """Tests for :func:`create_snapshot`."""

    def test_creates_snapshots_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            create_snapshot(course_dir, 1)

            snapshots_root = course_dir / SNAPSHOTS_DIR_NAME
            self.assertTrue(snapshots_root.is_dir())

    def test_creates_v0001_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshot_dir = create_snapshot(course_dir, 1)

            self.assertEqual(snapshot_dir.name, "v0001")
            self.assertTrue(snapshot_dir.is_dir())

    def test_creates_v0015_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshot_dir = create_snapshot(course_dir, 15)

            self.assertEqual(snapshot_dir.name, "v0015")
            self.assertTrue(snapshot_dir.is_dir())

    def test_copies_course_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshot_dir = create_snapshot(course_dir, 1)

            course_json = snapshot_dir / "course.json"
            self.assertTrue(course_json.is_file())
            manifest = json.loads(course_json.read_text(encoding="utf-8"))
            self.assertEqual(manifest["title"], "Service Course")

    def test_copies_lesson_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshot_dir = create_snapshot(course_dir, 1)

            lesson_json = snapshot_dir / "lesson_01" / "lesson.json"
            self.assertTrue(lesson_json.is_file())
            lesson = json.loads(lesson_json.read_text(encoding="utf-8"))
            self.assertEqual(lesson["title"], "Lesson 1")

    def test_snapshots_directory_not_inside_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshot_dir = create_snapshot(course_dir, 1)

            nested_snapshots = snapshot_dir / SNAPSHOTS_DIR_NAME
            self.assertFalse(nested_snapshots.exists())

    def test_repeated_call_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            first_snapshot = create_snapshot(course_dir, 1)

            original_course_text = (first_snapshot / "course.json").read_text(
                encoding="utf-8"
            )

            (course_dir / "course.json").write_text(
                json.dumps({"title": "Changed Course"}),
                encoding="utf-8",
            )

            second_snapshot = create_snapshot(course_dir, 1)
            snapshot_course_text = (second_snapshot / "course.json").read_text(
                encoding="utf-8"
            )

            self.assertEqual(first_snapshot, second_snapshot)
            self.assertEqual(snapshot_course_text, original_course_text)

    def test_returns_snapshot_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshot_dir = create_snapshot(course_dir, 1)

            expected = course_dir / SNAPSHOTS_DIR_NAME / "v0001"
            self.assertEqual(snapshot_dir, expected)

    def test_missing_course_dir_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = Path(tmp) / "missing"
            with self.assertRaises(ValueError):
                create_snapshot(missing_dir, 1)
            self.assertFalse(missing_dir.exists())
            self.assertFalse((missing_dir / SNAPSHOTS_DIR_NAME).exists())

    def test_course_dir_as_file_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_path = Path(tmp) / "not_a_dir"
            course_path.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                create_snapshot(course_path, 1)
            self.assertFalse((course_path / SNAPSHOTS_DIR_NAME).exists())

    def test_version_zero_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            with self.assertRaises(ValueError):
                create_snapshot(course_dir, 0)
            self.assertFalse((course_dir / SNAPSHOTS_DIR_NAME / "v0000").exists())

    def test_negative_version_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            with self.assertRaises(ValueError):
                create_snapshot(course_dir, -1)
            self.assertFalse((course_dir / SNAPSHOTS_DIR_NAME).exists())

    def test_string_version_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            with self.assertRaises(ValueError):
                create_snapshot(course_dir, "1")  # type: ignore[arg-type]
            self.assertFalse((course_dir / SNAPSHOTS_DIR_NAME).exists())

    def test_bool_version_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            with self.assertRaises(ValueError):
                create_snapshot(course_dir, True)  # type: ignore[arg-type]
            self.assertFalse((course_dir / SNAPSHOTS_DIR_NAME).exists())

    def test_existing_snapshot_as_file_raises_file_exists_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshots_root = course_dir / SNAPSHOTS_DIR_NAME
            snapshots_root.mkdir()
            (snapshots_root / "v0001").write_text("not a dir", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                create_snapshot(course_dir, 1)

    def test_copytree_failure_leaves_no_partial_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            with patch(
                "app.content.snapshots.shutil.copytree",
                side_effect=OSError("copy failed"),
            ):
                with self.assertRaises(OSError):
                    create_snapshot(course_dir, 1)

            snapshots_root = course_dir / SNAPSHOTS_DIR_NAME
            self.assertFalse((snapshots_root / "v0001").exists())
            temp_dirs = [
                path
                for path in snapshots_root.iterdir()
                if path.is_dir() and path.name.startswith(".v0001.")
            ]
            self.assertEqual(temp_dirs, [])

    def test_preexisting_fixed_temp_path_is_not_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(Path(tmp))
            snapshots_root = course_dir / SNAPSHOTS_DIR_NAME
            snapshots_root.mkdir()
            preexisting_temp = snapshots_root / ".v0001.tmp"
            preexisting_temp.mkdir()
            (preexisting_temp / "marker.txt").write_text("keep", encoding="utf-8")

            snapshot_dir = create_snapshot(course_dir, 1)

            self.assertEqual(snapshot_dir.name, "v0001")
            self.assertTrue(snapshot_dir.is_dir())
            self.assertTrue(preexisting_temp.is_dir())
            self.assertEqual(
                (preexisting_temp / "marker.txt").read_text(encoding="utf-8"),
                "keep",
            )


if __name__ == "__main__":
    unittest.main()
