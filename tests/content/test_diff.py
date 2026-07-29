"""Tests for snapshot comparison (``app.content.diff``)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.content.diff import SnapshotDiff, compare_snapshots


def _write_file(directory: Path, relative_path: str, content: bytes) -> Path:
    """Create a file under ``directory`` and return its absolute path."""
    file_path = directory / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    return file_path


def _create_snapshot(root: Path, slug: str, files: dict[str, bytes]) -> Path:
    """Create a snapshot directory with the given relative file contents."""
    snapshot_dir = root / slug
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        _write_file(snapshot_dir, relative_path, content)
    return snapshot_dir


class CompareSnapshotsTests(unittest.TestCase):
    """Tests for :func:`compare_snapshots`."""

    def test_identical_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "course.json": b'{"title": "Brands"}',
                "lesson_01/lesson.json": b'{"title": "Lesson 1"}',
            }
            old_snapshot = _create_snapshot(root, "old", files)
            new_snapshot = _create_snapshot(root, "new", files)

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [])
        self.assertEqual(diff.removed_files, [])
        self.assertEqual(diff.changed_files, [])
        self.assertEqual(
            diff.unchanged_files,
            [Path("course.json"), Path("lesson_01/lesson.json")],
        )

    def test_added_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(
                root,
                "old",
                {"course.json": b'{"title": "Brands"}'},
            )
            new_snapshot = _create_snapshot(
                root,
                "new",
                {
                    "course.json": b'{"title": "Brands"}',
                    "quiz.json": b'{"title": "Quiz"}',
                },
            )

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [Path("quiz.json")])
        self.assertEqual(diff.removed_files, [])
        self.assertEqual(diff.changed_files, [])
        self.assertEqual(diff.unchanged_files, [Path("course.json")])

    def test_removed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(
                root,
                "old",
                {
                    "course.json": b'{"title": "Brands"}',
                    "quiz.json": b'{"title": "Quiz"}',
                },
            )
            new_snapshot = _create_snapshot(
                root,
                "new",
                {"course.json": b'{"title": "Brands"}'},
            )

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [])
        self.assertEqual(diff.removed_files, [Path("quiz.json")])
        self.assertEqual(diff.changed_files, [])
        self.assertEqual(diff.unchanged_files, [Path("course.json")])

    def test_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(
                root,
                "old",
                {"course.json": b'{"title": "Brands", "version": 1}'},
            )
            new_snapshot = _create_snapshot(
                root,
                "new",
                {"course.json": b'{"title": "Brands", "version": 2}'},
            )

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [])
        self.assertEqual(diff.removed_files, [])
        self.assertEqual(diff.changed_files, [Path("course.json")])
        self.assertEqual(diff.unchanged_files, [])

    def test_multiple_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(
                root,
                "old",
                {
                    "course.json": b"v1",
                    "lesson_01/lesson.json": b"old lesson",
                    "lesson_02/lesson.json": b"remove me",
                    "cover.jpg": b"cover",
                },
            )
            new_snapshot = _create_snapshot(
                root,
                "new",
                {
                    "course.json": b"v2",
                    "lesson_01/lesson.json": b"old lesson",
                    "lesson_03/lesson.json": b"new lesson",
                    "cover.jpg": b"cover",
                },
            )

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [Path("lesson_03/lesson.json")])
        self.assertEqual(diff.removed_files, [Path("lesson_02/lesson.json")])
        self.assertEqual(diff.changed_files, [Path("course.json")])
        self.assertEqual(
            diff.unchanged_files,
            [Path("cover.jpg"), Path("lesson_01/lesson.json")],
        )

    def test_missing_old_snapshot_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            new_snapshot = _create_snapshot(root, "new", {"course.json": b"{}"})
            missing_old = root / "missing-old"

            with self.assertRaises(ValueError) as context:
                compare_snapshots(missing_old, new_snapshot)

        self.assertIn("does not exist", str(context.exception))

    def test_missing_new_snapshot_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(root, "old", {"course.json": b"{}"})
            missing_new = root / "missing-new"

            with self.assertRaises(ValueError) as context:
                compare_snapshots(old_snapshot, missing_new)

        self.assertIn("does not exist", str(context.exception))

    def test_old_snapshot_as_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_file = root / "old"
            old_file.write_bytes(b"not a directory")
            new_snapshot = _create_snapshot(root, "new", {"course.json": b"{}"})

            with self.assertRaises(ValueError) as context:
                compare_snapshots(old_file, new_snapshot)

        self.assertIn("not a directory", str(context.exception))

    def test_new_snapshot_as_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(root, "old", {"course.json": b"{}"})
            new_file = root / "new"
            new_file.write_bytes(b"not a directory")

            with self.assertRaises(ValueError) as context:
                compare_snapshots(old_snapshot, new_file)

        self.assertIn("not a directory", str(context.exception))

    def test_results_are_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(
                root,
                "old",
                {
                    "z.txt": b"z",
                    "a.txt": b"a-old",
                    "m.txt": b"m",
                },
            )
            new_snapshot = _create_snapshot(
                root,
                "new",
                {
                    "z.txt": b"z",
                    "a.txt": b"a-new",
                    "b.txt": b"b",
                },
            )

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [Path("b.txt")])
        self.assertEqual(diff.removed_files, [Path("m.txt")])
        self.assertEqual(diff.changed_files, [Path("a.txt")])
        self.assertEqual(diff.unchanged_files, [Path("z.txt")])

    def test_empty_directories_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_snapshot = _create_snapshot(root, "old", {"course.json": b"{}"})
            new_snapshot = _create_snapshot(root, "new", {"course.json": b"{}"})
            (old_snapshot / "empty_lesson").mkdir()
            (new_snapshot / "empty_lesson").mkdir()

            diff = compare_snapshots(old_snapshot, new_snapshot)

        self.assertEqual(diff.added_files, [])
        self.assertEqual(diff.removed_files, [])
        self.assertEqual(diff.changed_files, [])
        self.assertEqual(diff.unchanged_files, [Path("course.json")])

    def test_return_type_is_snapshot_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = _create_snapshot(root, "snap", {"course.json": b"{}"})

            diff = compare_snapshots(snapshot, snapshot)

        self.assertIsInstance(diff, SnapshotDiff)


if __name__ == "__main__":
    unittest.main()
