"""Tests for the safe course publisher (``app.content.publisher``)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from app.content.history import PUBLISH_HISTORY_FILENAME
from app.content.publisher import RELEASE_MANIFEST_FILENAME, publish_course
from app.content.release_manifest_io import load_release_manifest
from app.content.snapshots import SNAPSHOTS_DIR_NAME
from app.content.validator import validate_course


def _create_course_dir(
    courses_dir: Path,
    slug: str = "test",
    *,
    course_manifest: Optional[dict] = None,
    with_lesson: bool = True,
    with_lesson_json: bool = True,
    write_course_json: bool = True,
    course_json_text: Optional[str] = None,
) -> Path:
    """Create a course directory for publisher tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    if course_json_text is not None:
        (course_dir / "course.json").write_text(course_json_text, encoding="utf-8")
    elif write_course_json:
        manifest = course_manifest if course_manifest is not None else {}
        (course_dir / "course.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

    if with_lesson:
        lesson_dir = course_dir / "lesson_01"
        lesson_dir.mkdir()
        if with_lesson_json:
            (lesson_dir / "lesson.json").write_text("{}", encoding="utf-8")

    return course_dir


class PublishCourseTests(unittest.TestCase):
    """Tests for :func:`publish_course`."""

    def test_ready_draft_becomes_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            result = publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))

        self.assertTrue(result["published"])
        self.assertTrue(result["gate"]["allowed"])
        self.assertEqual(manifest["status"], "published")
        self.assertEqual(manifest["title"], "Draft Course")
        self.assertEqual(manifest["version"], 1)

    def test_missing_version_becomes_one_on_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], 1)

    def test_version_one_becomes_two_on_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course", "version": 1},
            )
            publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], 2)

    def test_version_five_becomes_six_on_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course", "version": 5},
            )
            publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], 6)

    def test_publish_preserves_other_manifest_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={
                    "status": "draft",
                    "title": "My Course",
                    "version": 2,
                    "order": 3,
                },
            )
            publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["status"], "published")
        self.assertEqual(manifest["title"], "My Course")
        self.assertEqual(manifest["version"], 3)
        self.assertEqual(manifest["order"], 3)

    def test_validation_error_blocks_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft"},
            )
            for lesson_slug in ("lesson_01", "lesson_02"):
                lesson_dir = course_dir / lesson_slug
                lesson_dir.mkdir(exist_ok=True)
                (lesson_dir / "lesson.json").write_text(
                    '{"order": 1}',
                    encoding="utf-8",
                )

            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            result = publish_course(course_dir)

            self.assertFalse(result["published"])
            self.assertFalse(result["gate"]["allowed"])
            self.assertEqual(
                (course_dir / "course.json").read_text(encoding="utf-8"),
                original_text,
            )

    def test_already_published_course_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={
                    "status": "published",
                    "title": "Published Course",
                    "version": 1,
                },
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            original_manifest = json.loads(original_text)
            result = publish_course(course_dir)

            final_text = (course_dir / "course.json").read_text(encoding="utf-8")
            manifest = json.loads(final_text)

        self.assertTrue(result["published"])
        self.assertTrue(result["gate"]["allowed"])
        self.assertEqual(manifest["status"], "published")
        self.assertEqual(manifest["title"], original_manifest["title"])
        self.assertEqual(manifest["version"], original_manifest["version"])
        self.assertEqual(final_text, original_text)

    def test_already_published_does_not_increment_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={
                    "status": "published",
                    "title": "Published Course",
                    "version": 3,
                },
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            publish_course(course_dir)
            final_text = (course_dir / "course.json").read_text(encoding="utf-8")

        self.assertEqual(final_text, original_text)

    def test_string_version_blocks_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course", "version": "2"},
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            result = publish_course(course_dir)
            final_text = (course_dir / "course.json").read_text(encoding="utf-8")

        self.assertFalse(result["published"])
        self.assertFalse(result["gate"]["allowed"])
        self.assertGreater(result["gate"]["errors"], 0)
        self.assertEqual(final_text, original_text)

    def test_negative_version_blocks_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course", "version": -1},
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            result = publish_course(course_dir)
            final_text = (course_dir / "course.json").read_text(encoding="utf-8")

        self.assertFalse(result["published"])
        self.assertFalse(result["gate"]["allowed"])
        self.assertGreater(result["gate"]["errors"], 0)
        self.assertEqual(final_text, original_text)

    def test_bool_version_blocks_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course", "version": True},
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            result = publish_course(course_dir)
            final_text = (course_dir / "course.json").read_text(encoding="utf-8")

        self.assertFalse(result["published"])
        self.assertFalse(result["gate"]["allowed"])
        self.assertGreater(result["gate"]["errors"], 0)
        self.assertEqual(final_text, original_text)

    def test_failed_release_gate_does_not_change_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course", "version": 2},
                with_lesson=False,
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            result = publish_course(course_dir)
            final_text = (course_dir / "course.json").read_text(encoding="utf-8")

        self.assertFalse(result["published"])
        self.assertEqual(final_text, original_text)

    def test_warnings_do_not_block_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={
                    "status": "draft",
                    "title": "Draft Course",
                    "description": "Short",
                },
            )
            result = publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))

        self.assertTrue(result["published"])
        self.assertTrue(result["gate"]["allowed"])
        self.assertGreater(result["gate"]["warnings"], 0)
        self.assertEqual(result["gate"]["errors"], 0)
        self.assertEqual(manifest["status"], "published")

    def test_empty_draft_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Empty Draft"},
                with_lesson=False,
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            result = publish_course(course_dir)
            final_text = (course_dir / "course.json").read_text(encoding="utf-8")

            with tempfile.TemporaryDirectory() as candidate_tmp:
                candidate_dir = Path(candidate_tmp) / course_dir.name
                shutil.copytree(course_dir, candidate_dir)
                candidate_manifest = json.loads(
                    (candidate_dir / "course.json").read_text(encoding="utf-8")
                )
                candidate_manifest["status"] = "published"
                (candidate_dir / "course.json").write_text(
                    json.dumps(candidate_manifest),
                    encoding="utf-8",
                )
                candidate_report = validate_course(candidate_dir)
                error_codes = {
                    issue.code
                    for issue in candidate_report.errors
                }

            self.assertFalse(result["published"])
            self.assertFalse(result["gate"]["allowed"])
            self.assertGreater(result["gate"]["errors"], 0)
            self.assertIn("published_course_without_lessons", error_codes)
            self.assertEqual(final_text, original_text)

    def test_missing_course_json_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                write_course_json=False,
                with_lesson=False,
            )
            result = publish_course(course_dir)

            self.assertFalse(result["published"])
            self.assertFalse(result["gate"]["allowed"])
            self.assertFalse((course_dir / "course.json").exists())

    def test_invalid_course_json_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            invalid_json = "{ invalid json"
            course_dir = _create_course_dir(
                Path(tmp),
                course_json_text=invalid_json,
                with_lesson=False,
            )
            result = publish_course(course_dir)

            self.assertFalse(result["published"])
            self.assertFalse(result["gate"]["allowed"])
            self.assertEqual(
                (course_dir / "course.json").read_text(encoding="utf-8"),
                invalid_json,
            )


class PublishCourseIntegrationTests(unittest.TestCase):
    """Integration tests for the publication pipeline."""

    def test_successful_publication_creates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            snapshot_dir = course_dir / SNAPSHOTS_DIR_NAME / "v0001"
            self.assertTrue(snapshot_dir.is_dir())
            self.assertTrue((snapshot_dir / "course.json").is_file())
            self.assertTrue((snapshot_dir / "lesson_01" / "lesson.json").is_file())

    def test_successful_publication_creates_release_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            manifest_path = (
                course_dir / SNAPSHOTS_DIR_NAME / "v0001" / RELEASE_MANIFEST_FILENAME
            )
            manifest = load_release_manifest(manifest_path)

        self.assertEqual(manifest.version, 1)
        self.assertGreater(len(manifest.published), 0)
        self.assertIn(".snapshots/v0001", manifest.snapshot)
        self.assertGreater(manifest.added_files, 0)
        self.assertEqual(manifest.removed_files, 0)
        self.assertEqual(manifest.changed_files, 0)
        self.assertEqual(manifest.unchanged_files, 0)

    def test_successful_publication_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            history = json.loads(
                (course_dir / PUBLISH_HISTORY_FILENAME).read_text(encoding="utf-8")
            )

        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["published"])
        self.assertEqual(history[0]["errors"], 0)

    def test_second_publication_compares_with_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
            manifest["status"] = "draft"
            manifest["title"] = "Updated Course"
            (course_dir / "course.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            publish_course(course_dir)

            manifest_path = (
                course_dir / SNAPSHOTS_DIR_NAME / "v0002" / RELEASE_MANIFEST_FILENAME
            )
            release_manifest = load_release_manifest(manifest_path)

            self.assertEqual(release_manifest.version, 2)
            self.assertEqual(release_manifest.changed_files, 1)
            self.assertEqual(release_manifest.added_files, 0)
            self.assertEqual(release_manifest.removed_files, 0)
            self.assertEqual(release_manifest.unchanged_files, 1)

    def test_release_manifest_does_not_affect_diff_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            v0001_manifest_path = (
                course_dir / SNAPSHOTS_DIR_NAME / "v0001" / RELEASE_MANIFEST_FILENAME
            )
            self.assertTrue(v0001_manifest_path.is_file())

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
            manifest["status"] = "draft"
            manifest["title"] = "Updated Course"
            (course_dir / "course.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            publish_course(course_dir)

            v0002_manifest_path = (
                course_dir / SNAPSHOTS_DIR_NAME / "v0002" / RELEASE_MANIFEST_FILENAME
            )
            release_manifest = load_release_manifest(v0002_manifest_path)

            self.assertTrue(v0001_manifest_path.is_file())
            self.assertTrue(v0002_manifest_path.is_file())
            self.assertEqual(release_manifest.added_files, 0)
            self.assertEqual(release_manifest.removed_files, 0)
            self.assertEqual(release_manifest.changed_files, 1)
            self.assertEqual(release_manifest.unchanged_files, 1)

    def test_previous_snapshot_manifest_is_not_modified_during_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            publish_course(course_dir)

            v0001_manifest_path = (
                course_dir / SNAPSHOTS_DIR_NAME / "v0001" / RELEASE_MANIFEST_FILENAME
            )
            original_manifest_bytes = v0001_manifest_path.read_bytes()

            manifest = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
            manifest["status"] = "draft"
            manifest["title"] = "Updated Course"
            (course_dir / "course.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            publish_course(course_dir)

            final_manifest_bytes = v0001_manifest_path.read_bytes()

            self.assertEqual(final_manifest_bytes, original_manifest_bytes)

    def test_already_published_does_not_run_publication_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={
                    "status": "published",
                    "title": "Published Course",
                    "version": 1,
                },
            )
            publish_course(course_dir)

            snapshots_root = course_dir / SNAPSHOTS_DIR_NAME
            history_path = course_dir / PUBLISH_HISTORY_FILENAME

        self.assertFalse(snapshots_root.exists())
        self.assertFalse(history_path.exists())

    @patch("app.content.publisher.save_release_manifest", side_effect=OSError("disk full"))
    def test_pipeline_failure_restores_course_json(self, _mock_save) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = _create_course_dir(
                Path(tmp),
                course_manifest={"status": "draft", "title": "Draft Course"},
            )
            original_text = (course_dir / "course.json").read_text(encoding="utf-8")
            snapshot_dir = course_dir / SNAPSHOTS_DIR_NAME / "v0001"

            with self.assertRaises(OSError):
                publish_course(course_dir)

            final_text = (course_dir / "course.json").read_text(encoding="utf-8")
            manifest = json.loads(final_text)

        self.assertEqual(final_text, original_text)
        self.assertEqual(manifest["status"], "draft")
        self.assertFalse(snapshot_dir.exists())


if __name__ == "__main__":
    unittest.main()
