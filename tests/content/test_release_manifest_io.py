"""Tests for release manifest I/O (``app.content.release_manifest_io``)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.content.release_manifest import ReleaseManifest
from app.content.release_manifest_io import (
    load_release_manifest,
    save_release_manifest,
)


def _sample_manifest(**overrides: object) -> ReleaseManifest:
    """Build a sample release manifest for tests."""
    defaults = {
        "version": 2,
        "published": "2026-07-29T12:00:00Z",
        "snapshot": "courses/brands/.snapshots/v0002",
        "added_files": 1,
        "removed_files": 0,
        "changed_files": 2,
        "unchanged_files": 5,
    }
    defaults.update(overrides)
    return ReleaseManifest(**defaults)  # type: ignore[arg-type]


def _write_manifest_json(path: Path, **overrides: object) -> None:
    """Write a minimal valid manifest JSON with optional field overrides."""
    data = {
        "version": 1,
        "published": "2026-01-01T00:00:00Z",
        "snapshot": "courses/test/.snapshots/v0001",
        "added_files": 0,
        "removed_files": 0,
        "changed_files": 0,
        "unchanged_files": 0,
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")


class SaveLoadReleaseManifestTests(unittest.TestCase):
    """Round-trip and encoding tests for release manifest I/O."""

    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            manifest = _sample_manifest()

            save_release_manifest(manifest, path)
            loaded = load_release_manifest(path)

        self.assertEqual(loaded, manifest)

    def test_unicode_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            manifest = _sample_manifest(
                published="2026-07-29T12:00:00Z — опубликовано",
                snapshot="courses/бренды/.snapshots/v0001",
            )

            save_release_manifest(manifest, path)
            raw_text = path.read_text(encoding="utf-8")
            loaded = load_release_manifest(path)

        self.assertIn("опубликовано", raw_text)
        self.assertIn("бренды", raw_text)
        self.assertNotIn("\\u", raw_text)
        self.assertEqual(loaded.published, manifest.published)
        self.assertEqual(loaded.snapshot, manifest.snapshot)

    def test_saved_json_uses_utf8_indent_and_field_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            manifest = _sample_manifest()

            save_release_manifest(manifest, path)
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)

            self.assertEqual(
                set(data.keys()),
                {
                    "version",
                    "published",
                    "snapshot",
                    "added_files",
                    "removed_files",
                    "changed_files",
                    "unchanged_files",
                },
            )
            self.assertEqual(data["version"], 2)
            self.assertEqual(data["added_files"], 1)
            self.assertTrue(raw_text.startswith("{\n"))

    def test_atomic_write_preserves_existing_file_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text('{"original": true}', encoding="utf-8")
            manifest = _sample_manifest()

            original_replace = os.replace

            def failing_replace(src: str, dst: str) -> None:
                if Path(dst) == path:
                    raise OSError("simulated atomic rename failure")
                original_replace(src, dst)

            with mock.patch("os.replace", side_effect=failing_replace):
                with self.assertRaises(OSError):
                    save_release_manifest(manifest, path)

            self.assertEqual(path.read_text(encoding="utf-8"), '{"original": true}')
            temp_files = list(Path(tmp).glob(".release-manifest.json.*.tmp"))
            self.assertEqual(temp_files, [])


class LoadReleaseManifestValidationTests(unittest.TestCase):
    """Validation and error handling for :func:`load_release_manifest`."""

    def test_missing_file_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"

            with self.assertRaises(FileNotFoundError):
                load_release_manifest(path)

    def test_invalid_json_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text("{not valid json", encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("Invalid JSON", str(context.exception))

    def test_missing_required_field_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "published": "2026-01-01T00:00:00Z",
                        "snapshot": "courses/test/.snapshots/v0001",
                        "added_files": 0,
                        "removed_files": 0,
                        "changed_files": 0,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("missing required fields", str(context.exception))
        self.assertIn("unchanged_files", str(context.exception))

    def test_extra_field_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            manifest = _sample_manifest()
            data = {
                "version": manifest.version,
                "published": manifest.published,
                "snapshot": manifest.snapshot,
                "added_files": manifest.added_files,
                "removed_files": manifest.removed_files,
                "changed_files": manifest.changed_files,
                "unchanged_files": manifest.unchanged_files,
                "extra": "field",
            }
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("unexpected fields", str(context.exception))
        self.assertIn("extra", str(context.exception))

    def test_bool_version_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": True,
                        "published": "2026-01-01T00:00:00Z",
                        "snapshot": "courses/test/.snapshots/v0001",
                        "added_files": 0,
                        "removed_files": 0,
                        "changed_files": 0,
                        "unchanged_files": 0,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("version", str(context.exception))
        self.assertIn("integer", str(context.exception))

    def test_bool_count_field_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "published": "2026-01-01T00:00:00Z",
                        "snapshot": "courses/test/.snapshots/v0001",
                        "added_files": False,
                        "removed_files": 0,
                        "changed_files": 0,
                        "unchanged_files": 0,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("added_files", str(context.exception))
        self.assertIn("integer", str(context.exception))

    def test_wrong_string_field_type_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "published": 123,
                        "snapshot": "courses/test/.snapshots/v0001",
                        "added_files": 0,
                        "removed_files": 0,
                        "changed_files": 0,
                        "unchanged_files": 0,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("published", str(context.exception))
        self.assertIn("string", str(context.exception))

    def test_wrong_int_field_type_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "published": "2026-01-01T00:00:00Z",
                        "snapshot": "courses/test/.snapshots/v0001",
                        "added_files": "1",
                        "removed_files": 0,
                        "changed_files": 0,
                        "unchanged_files": 0,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("added_files", str(context.exception))
        self.assertIn("integer", str(context.exception))

    def test_non_object_root_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("JSON object", str(context.exception))

    def test_empty_published_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, published="")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("published", str(context.exception))
        self.assertIn("empty", str(context.exception))

    def test_whitespace_only_published_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, published="   ")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("published", str(context.exception))
        self.assertIn("empty", str(context.exception))

    def test_empty_snapshot_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, snapshot="")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("snapshot", str(context.exception))
        self.assertIn("empty", str(context.exception))

    def test_whitespace_only_snapshot_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, snapshot="   ")

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("snapshot", str(context.exception))
        self.assertIn("empty", str(context.exception))

    def test_negative_added_files_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, added_files=-1)

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("added_files", str(context.exception))
        self.assertIn("at least 0", str(context.exception))

    def test_negative_removed_files_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, removed_files=-1)

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("removed_files", str(context.exception))
        self.assertIn("at least 0", str(context.exception))

    def test_negative_changed_files_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, changed_files=-1)

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("changed_files", str(context.exception))
        self.assertIn("at least 0", str(context.exception))

    def test_negative_unchanged_files_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-manifest.json"
            _write_manifest_json(path, unchanged_files=-1)

            with self.assertRaises(ValueError) as context:
                load_release_manifest(path)

        self.assertIn("unchanged_files", str(context.exception))
        self.assertIn("at least 0", str(context.exception))


if __name__ == "__main__":
    unittest.main()
