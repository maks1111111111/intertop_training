"""Tests for publication history (``app.content.history``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.content.history import PUBLISH_HISTORY_FILENAME, record_publication


class RecordPublicationTests(unittest.TestCase):
    """Tests for :func:`record_publication`."""

    def test_creates_new_history_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()

            record_publication(
                course_dir,
                published=True,
                gate={"allowed": True, "ready": True, "errors": 0, "warnings": 0},
            )

            history_path = course_dir / PUBLISH_HISTORY_FILENAME
            self.assertTrue(history_path.exists())

            history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["published"])
        self.assertEqual(history[0]["errors"], 0)
        self.assertEqual(history[0]["warnings"], 0)
        self.assertIn("timestamp", history[0])
        self.assertTrue(history[0]["timestamp"].endswith("Z"))

    def test_appends_second_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()

            record_publication(
                course_dir,
                published=False,
                gate={"allowed": False, "ready": False, "errors": 2, "warnings": 1},
            )
            record_publication(
                course_dir,
                published=True,
                gate={"allowed": True, "ready": True, "errors": 0, "warnings": 3},
            )

            history = json.loads(
                (course_dir / PUBLISH_HISTORY_FILENAME).read_text(encoding="utf-8")
            )

        self.assertEqual(len(history), 2)

    def test_preserves_entry_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()

            record_publication(
                course_dir,
                published=False,
                gate={"errors": 1, "warnings": 0},
            )
            record_publication(
                course_dir,
                published=False,
                gate={"errors": 2, "warnings": 0},
            )
            record_publication(
                course_dir,
                published=True,
                gate={"errors": 0, "warnings": 1},
            )

            history = json.loads(
                (course_dir / PUBLISH_HISTORY_FILENAME).read_text(encoding="utf-8")
            )

        self.assertFalse(history[0]["published"])
        self.assertEqual(history[0]["errors"], 1)
        self.assertFalse(history[1]["published"])
        self.assertEqual(history[1]["errors"], 2)
        self.assertTrue(history[2]["published"])
        self.assertEqual(history[2]["warnings"], 1)

    def test_records_published_errors_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()

            record_publication(
                course_dir,
                published=False,
                gate={
                    "allowed": False,
                    "ready": False,
                    "errors": 4,
                    "warnings": 7,
                },
            )

            history = json.loads(
                (course_dir / PUBLISH_HISTORY_FILENAME).read_text(encoding="utf-8")
            )

        entry = history[0]
        self.assertFalse(entry["published"])
        self.assertEqual(entry["errors"], 4)
        self.assertEqual(entry["warnings"], 7)


class CorruptedHistoryTests(unittest.TestCase):
    """Tests for safe handling of corrupted publication history files."""

    def _write_history(self, course_dir: Path, content: str) -> Path:
        history_path = course_dir / PUBLISH_HISTORY_FILENAME
        history_path.write_text(content, encoding="utf-8")
        return history_path

    def test_invalid_json_raises_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            history_path = self._write_history(course_dir, "{not valid json")

            original_content = history_path.read_text(encoding="utf-8")

            with self.assertRaises(ValueError):
                record_publication(
                    course_dir,
                    published=True,
                    gate={"errors": 0, "warnings": 0},
                )

            self.assertEqual(
                history_path.read_text(encoding="utf-8"),
                original_content,
            )

    def test_json_object_root_raises_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            history_path = self._write_history(
                course_dir,
                json.dumps({"timestamp": "2026-01-01T00:00:00Z"}),
            )

            original_content = history_path.read_text(encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                record_publication(
                    course_dir,
                    published=True,
                    gate={"errors": 0, "warnings": 0},
                )

            self.assertIn("JSON array", str(context.exception))
            self.assertEqual(
                history_path.read_text(encoding="utf-8"),
                original_content,
            )

    def test_non_dict_entry_raises_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            history_path = self._write_history(
                course_dir,
                json.dumps(["not-an-object"]),
            )

            original_content = history_path.read_text(encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                record_publication(
                    course_dir,
                    published=True,
                    gate={"errors": 0, "warnings": 0},
                )

            self.assertIn("index 0", str(context.exception))
            self.assertEqual(
                history_path.read_text(encoding="utf-8"),
                original_content,
            )

    def test_missing_history_file_is_created_normally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            history_path = course_dir / PUBLISH_HISTORY_FILENAME

            self.assertFalse(history_path.exists())

            record_publication(
                course_dir,
                published=True,
                gate={"errors": 0, "warnings": 0},
            )

            history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["published"])
