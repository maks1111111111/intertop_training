"""Tests for content pack building (``app.content.content_pack``)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from app.content.content_pack import (
    RELEASE_MANIFEST_FILENAME,
    ContentPack,
    build_content_pack,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _create_snapshot(
    root: Path,
    *,
    slug: str = "brands",
    version: int = 1,
) -> tuple[Path, Path]:
    """Create a course directory and snapshot with several files."""
    course_dir = root / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {"title": "Brands Course", "status": "published", "version": version},
        ),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "Lesson 1"}),
        encoding="utf-8",
    )
    (lesson_dir / "notes.txt").write_bytes(b"lesson notes")

    snapshot_dir = course_dir / ".snapshots" / f"v{version:04d}"
    snapshot_dir.mkdir(parents=True)
    shutil.copytree(
        course_dir,
        snapshot_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".snapshots"),
    )

    return course_dir, snapshot_dir


class BuildContentPackTests(unittest.TestCase):
    """Tests for :func:`build_content_pack`."""

    def test_builds_pack_from_snapshot_with_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))

            pack = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertIsInstance(pack, ContentPack)
            self.assertEqual(pack.course_slug, "brands")
            self.assertEqual(pack.version, 1)
            self.assertEqual(pack.snapshot, snapshot_dir.as_posix())
            self.assertEqual(
                pack.files,
                (
                    "course.json",
                    "lesson_01/lesson.json",
                    "lesson_01/notes.txt",
                ),
            )
            self.assertEqual(pack.files_count, 3)
            self.assertGreater(pack.total_size_bytes, 0)
            self.assertTrue(_SHA256_PATTERN.match(pack.checksum_sha256))

    def test_checksum_is_deterministic_across_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a:
            with tempfile.TemporaryDirectory() as tmp_b:
                course_a, snapshot_a = _create_snapshot(Path(tmp_a))
                course_b, snapshot_b = _create_snapshot(Path(tmp_b))

                pack_a = build_content_pack(course_a, snapshot_a, 1)
                pack_b = build_content_pack(course_b, snapshot_b, 1)

                self.assertEqual(pack_a.checksum_sha256, pack_b.checksum_sha256)
                self.assertEqual(pack_a.files, pack_b.files)
                self.assertEqual(pack_a.total_size_bytes, pack_b.total_size_bytes)

    def test_binary_files_with_null_bytes_are_handled_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "binary_course"
            course_dir.mkdir()
            snapshot_dir = course_dir / "snap"
            snapshot_dir.mkdir()
            binary_path = snapshot_dir / "data.bin"
            binary_path.write_bytes(b"\x00\x01\xff\x00\xfe")

            first = build_content_pack(course_dir, snapshot_dir, 1)
            second = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertEqual(first.checksum_sha256, second.checksum_sha256)
            self.assertTrue(_SHA256_PATTERN.match(first.checksum_sha256))

            binary_path.write_bytes(b"\x00\x01\xff\x00\xfd")
            changed = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertNotEqual(first.checksum_sha256, changed.checksum_sha256)

    def test_length_prefixed_checksum_avoids_null_separator_collision(self) -> None:
        """Regression for ambiguous null-byte separator framing."""

        def _separator_based_checksum(files: list[tuple[str, bytes]]) -> str:
            digest = hashlib.sha256()
            for relative_path, content in sorted(files, key=lambda item: item[0]):
                digest.update(relative_path.encode("utf-8"))
                digest.update(b"\x00")
                digest.update(content)
                digest.update(b"\x00")
            return digest.hexdigest()

        def _length_prefixed_checksum(files: list[tuple[str, bytes]]) -> str:
            digest = hashlib.sha256()
            for relative_path, content in sorted(files, key=lambda item: item[0]):
                path_bytes = relative_path.encode("utf-8")
                digest.update(len(path_bytes).to_bytes(8, "big"))
                digest.update(path_bytes)
                digest.update(len(content).to_bytes(8, "big"))
                digest.update(content)
            return digest.hexdigest()

        ambiguous_a = [("a", b"\x00b")]
        ambiguous_b = [("a\x00", b"b")]

        self.assertEqual(
            _separator_based_checksum(ambiguous_a),
            _separator_based_checksum(ambiguous_b),
        )
        self.assertNotEqual(
            _length_prefixed_checksum(ambiguous_a),
            _length_prefixed_checksum(ambiguous_b),
        )

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "course"
            course_dir.mkdir()
            snapshot_dir = course_dir / "snap"
            snapshot_dir.mkdir()
            (snapshot_dir / "a").write_bytes(b"\x00b")

            pack = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertEqual(
                pack.checksum_sha256,
                _length_prefixed_checksum(ambiguous_a),
            )
            self.assertNotEqual(
                pack.checksum_sha256,
                _separator_based_checksum(ambiguous_a),
            )

    def test_changing_file_content_changes_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            original = build_content_pack(course_dir, snapshot_dir, 1)

            (snapshot_dir / "course.json").write_text(
                json.dumps({"title": "Changed Course"}),
                encoding="utf-8",
            )
            changed = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertNotEqual(original.checksum_sha256, changed.checksum_sha256)

    def test_changing_file_name_changes_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            original = build_content_pack(course_dir, snapshot_dir, 1)

            old_path = snapshot_dir / "lesson_01" / "notes.txt"
            new_path = snapshot_dir / "lesson_01" / "details.txt"
            old_path.rename(new_path)

            renamed = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertNotEqual(original.checksum_sha256, renamed.checksum_sha256)
            self.assertIn("lesson_01/details.txt", renamed.files)
            self.assertNotIn("lesson_01/notes.txt", renamed.files)

    def test_adding_file_changes_checksum_and_files_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            original = build_content_pack(course_dir, snapshot_dir, 1)

            (snapshot_dir / "quiz.json").write_text("{}", encoding="utf-8")
            updated = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertEqual(updated.files_count, original.files_count + 1)
            self.assertNotEqual(original.checksum_sha256, updated.checksum_sha256)
            self.assertIn("quiz.json", updated.files)

    def test_release_manifest_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            manifest_path = snapshot_dir / RELEASE_MANIFEST_FILENAME
            manifest_path.write_text("{}", encoding="utf-8")

            pack_without_manifest = build_content_pack(course_dir, snapshot_dir, 1)

            manifest_path.write_text('{"version": 99}', encoding="utf-8")
            pack_with_changed_manifest = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertNotIn(RELEASE_MANIFEST_FILENAME, pack_without_manifest.files)
            self.assertEqual(
                pack_without_manifest.files_count,
                pack_with_changed_manifest.files_count,
            )
            self.assertEqual(
                pack_without_manifest.total_size_bytes,
                pack_with_changed_manifest.total_size_bytes,
            )
            self.assertEqual(
                pack_without_manifest.checksum_sha256,
                pack_with_changed_manifest.checksum_sha256,
            )

    def test_nested_files_use_relative_posix_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            nested_dir = snapshot_dir / "assets" / "images"
            nested_dir.mkdir(parents=True)
            (nested_dir / "cover.png").write_bytes(b"\x89PNG")

            pack = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertIn("assets/images/cover.png", pack.files)

    def test_empty_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "empty_course"
            course_dir.mkdir()
            snapshot_dir = course_dir / ".snapshots" / "v0001"
            snapshot_dir.mkdir(parents=True)

            pack = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertEqual(pack.files, ())
            self.assertEqual(pack.files_count, 0)
            self.assertEqual(pack.total_size_bytes, 0)
            self.assertEqual(
                pack.checksum_sha256,
                hashlib.sha256().hexdigest(),
            )
            self.assertTrue(_SHA256_PATTERN.match(pack.checksum_sha256))

    def test_bool_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))

            with self.assertRaises(ValueError):
                build_content_pack(course_dir, snapshot_dir, True)

    def test_zero_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))

            with self.assertRaises(ValueError):
                build_content_pack(course_dir, snapshot_dir, 0)

    def test_negative_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))

            with self.assertRaises(ValueError):
                build_content_pack(course_dir, snapshot_dir, -1)

    def test_missing_course_dir_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_course = Path(tmp) / "missing"
            snapshot_dir = Path(tmp) / "snapshot"
            snapshot_dir.mkdir()

            with self.assertRaises(FileNotFoundError):
                build_content_pack(missing_course, snapshot_dir, 1)

    def test_missing_snapshot_dir_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            missing_snapshot = course_dir / ".snapshots" / "v0001"

            with self.assertRaises(FileNotFoundError):
                build_content_pack(course_dir, missing_snapshot, 1)

    def test_course_dir_as_file_raises_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_file = Path(tmp) / "brands"
            course_file.write_text("not a directory", encoding="utf-8")
            snapshot_dir = Path(tmp) / "snapshot"
            snapshot_dir.mkdir()

            with self.assertRaises(NotADirectoryError):
                build_content_pack(course_file, snapshot_dir, 1)

    def test_snapshot_dir_as_file_raises_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            snapshot_file = course_dir / "snapshot"
            snapshot_file.write_text("not a directory", encoding="utf-8")

            with self.assertRaises(NotADirectoryError):
                build_content_pack(course_dir, snapshot_file, 1)

    def test_symlink_is_not_included(self) -> None:
        if os.name == "nt":
            raise unittest.SkipTest("Symlink creation is not reliable on Windows")

        with tempfile.TemporaryDirectory() as tmp:
            course_dir, snapshot_dir = _create_snapshot(Path(tmp))
            target = snapshot_dir / "lesson_01" / "notes.txt"
            link = snapshot_dir / "linked.txt"
            link.symlink_to(target)

            pack = build_content_pack(course_dir, snapshot_dir, 1)

            self.assertNotIn("linked.txt", pack.files)
            self.assertEqual(pack.files_count, 3)


if __name__ == "__main__":
    unittest.main()
