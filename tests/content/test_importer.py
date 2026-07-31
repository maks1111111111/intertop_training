"""Tests for the course import pipeline foundation (``app.content.importer``)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class ReadSourceTests(unittest.TestCase):
    """Tests for :meth:`CourseImporter.read_source`."""

    @patch("app.content.pdf_reader.PdfReader.read")
    def test_read_source_pdf_uses_pdf_reader(self, mock_read: MagicMock) -> None:
        mock_read.return_value = "extracted pdf text"
        importer = CourseImporter()
        path = Path("/tmp/course.pdf")

        result = importer.read_source(path)

        self.assertEqual(result, "extracted pdf text")
        mock_read.assert_called_once_with(path)

    @patch("app.content.docx_reader.DocxReader.read")
    def test_read_source_docx_uses_docx_reader(self, mock_read: MagicMock) -> None:
        mock_read.return_value = "extracted docx text"
        importer = CourseImporter()
        path = Path("/tmp/course.docx")

        result = importer.read_source(path)

        self.assertEqual(result, "extracted docx text")
        mock_read.assert_called_once_with(path)

    def test_missing_reader_raises_value_error(self) -> None:
        importer = CourseImporter()
        path = Path("/tmp/course.pptx")

        with self.assertRaises(ValueError) as context:
            importer.read_source(path)

        self.assertIn("No reader registered for source type: pptx", str(context.exception))

    def test_injected_mock_reader_via_constructor(self) -> None:
        mock_reader = MagicMock()
        mock_reader.read.return_value = "custom extracted text"
        importer = CourseImporter(readers={"pdf": mock_reader})
        path = Path("/tmp/course.pdf")

        result = importer.read_source(path)

        self.assertEqual(result, "custom extracted text")
        mock_reader.read.assert_called_once_with(path)


if __name__ == "__main__":
    unittest.main()
