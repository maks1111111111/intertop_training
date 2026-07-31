"""Tests for the course import pipeline foundation (``app.content.importer``)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content.importer import CourseImporter, ImportResult, ImportSource


class DetectSourceTests(unittest.TestCase):
    """Tests for :meth:`CourseImporter.detect_source`."""

    def setUp(self) -> None:
        self.importer = CourseImporter()

    def test_detect_source_pdf(self) -> None:
        path = Path("/tmp/course.pdf")

        source = self.importer.detect_source(path)

        self.assertEqual(source, ImportSource(path=path, source_type="pdf"))

    def test_detect_source_docx(self) -> None:
        path = Path("/tmp/course.docx")

        source = self.importer.detect_source(path)

        self.assertEqual(source, ImportSource(path=path, source_type="docx"))

    def test_detect_source_pptx(self) -> None:
        path = Path("/tmp/course.pptx")

        source = self.importer.detect_source(path)

        self.assertEqual(source, ImportSource(path=path, source_type="pptx"))

    def test_detect_source_mp4(self) -> None:
        path = Path("/tmp/course.mp4")

        source = self.importer.detect_source(path)

        self.assertEqual(source, ImportSource(path=path, source_type="mp4"))

    def test_unknown_format_raises_value_error(self) -> None:
        path = Path("/tmp/course.txt")

        with self.assertRaises(ValueError):
            self.importer.detect_source(path)


class PrepareImportTests(unittest.TestCase):
    """Tests for :meth:`CourseImporter.prepare_import`."""

    def setUp(self) -> None:
        self.importer = CourseImporter()

    def test_prepare_import_uses_detect_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lesson.pdf"

            with patch.object(
                self.importer,
                "detect_source",
                wraps=self.importer.detect_source,
            ) as detect_source_mock:
                result = self.importer.prepare_import(path)

            detect_source_mock.assert_called_once_with(path)

        self.assertIsInstance(result, ImportResult)
        self.assertEqual(result.source.path, path)
        self.assertEqual(result.source.source_type, "pdf")
        self.assertIsNotNone(result.imported_at)


if __name__ == "__main__":
    unittest.main()
