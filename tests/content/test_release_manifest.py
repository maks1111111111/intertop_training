"""Tests for release manifest building (``app.content.release_manifest``)."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.content.diff import SnapshotDiff
from app.content.release_manifest import ReleaseManifest, build_release_manifest


def _make_diff(
    *,
    added: list[str] | None = None,
    removed: list[str] | None = None,
    changed: list[str] | None = None,
    unchanged: list[str] | None = None,
) -> SnapshotDiff:
    """Create a :class:`SnapshotDiff` from string relative paths."""
    return SnapshotDiff(
        added_files=[Path(p) for p in (added or [])],
        removed_files=[Path(p) for p in (removed or [])],
        changed_files=[Path(p) for p in (changed or [])],
        unchanged_files=[Path(p) for p in (unchanged or [])],
    )


class BuildReleaseManifestTests(unittest.TestCase):
    """Tests for :func:`build_release_manifest`."""

    def test_builds_manifest_with_correct_fields(self) -> None:
        diff = _make_diff(
            added=["quiz.json"],
            removed=["old.txt"],
            changed=["course.json"],
            unchanged=["lesson_01/lesson.json", "cover.jpg"],
        )
        snapshot = Path("courses/brands/.snapshots/v0002")

        manifest = build_release_manifest(
            version=2,
            published="2026-07-29T12:00:00Z",
            snapshot=snapshot,
            diff=diff,
        )

        self.assertIsInstance(manifest, ReleaseManifest)
        self.assertEqual(manifest.version, 2)
        self.assertEqual(manifest.published, "2026-07-29T12:00:00Z")
        self.assertEqual(manifest.snapshot, "courses/brands/.snapshots/v0002")

    def test_counts_are_computed_from_diff(self) -> None:
        diff = _make_diff(
            added=["a.txt", "b.txt"],
            removed=["c.txt"],
            changed=["d.txt", "e.txt", "f.txt"],
            unchanged=["g.txt"],
        )

        manifest = build_release_manifest(
            version=1,
            published="2026-01-01T00:00:00Z",
            snapshot=Path("courses/test/.snapshots/v0001"),
            diff=diff,
        )

        self.assertEqual(manifest.added_files, 2)
        self.assertEqual(manifest.removed_files, 1)
        self.assertEqual(manifest.changed_files, 3)
        self.assertEqual(manifest.unchanged_files, 1)

    def test_snapshot_is_stored_as_posix_path(self) -> None:
        diff = _make_diff()
        snapshot = Path("courses") / "brands" / ".snapshots" / "v0001"

        manifest = build_release_manifest(
            version=1,
            published="2026-01-01T00:00:00Z",
            snapshot=snapshot,
            diff=diff,
        )

        self.assertEqual(manifest.snapshot, "courses/brands/.snapshots/v0001")
        self.assertNotIn("\\", manifest.snapshot)

    def test_version_zero_raises(self) -> None:
        diff = _make_diff()

        with self.assertRaises(ValueError) as context:
            build_release_manifest(
                version=0,
                published="2026-01-01T00:00:00Z",
                snapshot=Path("courses/test/.snapshots/v0001"),
                diff=diff,
            )

        self.assertIn("at least 1", str(context.exception))

    def test_negative_version_raises(self) -> None:
        diff = _make_diff()

        with self.assertRaises(ValueError) as context:
            build_release_manifest(
                version=-1,
                published="2026-01-01T00:00:00Z",
                snapshot=Path("courses/test/.snapshots/v0001"),
                diff=diff,
            )

        self.assertIn("at least 1", str(context.exception))

    def test_bool_version_raises(self) -> None:
        diff = _make_diff()

        with self.assertRaises(ValueError) as context:
            build_release_manifest(
                version=True,  # type: ignore[arg-type]
                published="2026-01-01T00:00:00Z",
                snapshot=Path("courses/test/.snapshots/v0001"),
                diff=diff,
            )

        self.assertIn("positive integer", str(context.exception))

    def test_empty_published_raises(self) -> None:
        diff = _make_diff()

        with self.assertRaises(ValueError) as context:
            build_release_manifest(
                version=1,
                published="",
                snapshot=Path("courses/test/.snapshots/v0001"),
                diff=diff,
            )

        self.assertIn("must not be empty", str(context.exception))

    def test_whitespace_only_published_raises(self) -> None:
        diff = _make_diff()

        with self.assertRaises(ValueError) as context:
            build_release_manifest(
                version=1,
                published="   ",
                snapshot=Path("courses/test/.snapshots/v0001"),
                diff=diff,
            )

        self.assertIn("must not be empty", str(context.exception))

    def test_empty_diff_produces_zero_counts(self) -> None:
        diff = _make_diff()

        manifest = build_release_manifest(
            version=1,
            published="2026-01-01T00:00:00Z",
            snapshot=Path("courses/test/.snapshots/v0001"),
            diff=diff,
        )

        self.assertEqual(manifest.added_files, 0)
        self.assertEqual(manifest.removed_files, 0)
        self.assertEqual(manifest.changed_files, 0)
        self.assertEqual(manifest.unchanged_files, 0)


if __name__ == "__main__":
    unittest.main()
