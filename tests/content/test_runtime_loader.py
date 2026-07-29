"""Tests for runtime content loading (``app.content.runtime_loader``)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.content.content_pack import ContentPack, build_content_pack
from app.content.runtime_loader import RuntimeContent, load_runtime_content


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
