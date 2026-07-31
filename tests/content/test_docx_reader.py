"""Tests for DOCX text extraction (``app.content.docx_reader``)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.content.docx_reader import DocxReader


def _make_paragraph(text: str) -> MagicMock:
    paragraph = MagicMock()
    paragraph.text = text
    return paragraph


class DocxReaderReadTests(unittest.TestCase):
    """Tests for :meth:`DocxReader.read`."""

    @patch("app.content.docx_reader._DocxDocument")
    def test_read_single_paragraph(self, mock_docx_document: MagicMock) -> None:
        path = Path("/tmp/course.docx")
        mock_document = MagicMock()
        mock_document.paragraphs = [_make_paragraph("Hello World")]
        mock_docx_document.return_value = mock_document

        result = DocxReader().read(path)

        self.assertEqual(result, "Hello World")
        mock_docx_document.assert_called_once_with(str(path))

    @patch("app.content.docx_reader._DocxDocument")
    def test_read_multiple_paragraphs(self, mock_docx_document: MagicMock) -> None:
        path = Path("/tmp/course.docx")
        mock_document = MagicMock()
        mock_document.paragraphs = [
            _make_paragraph("Paragraph 1"),
            _make_paragraph("Paragraph 2"),
        ]
        mock_docx_document.return_value = mock_document

        result = DocxReader().read(path)

        self.assertEqual(result, "Paragraph 1\nParagraph 2")

    @patch("app.content.docx_reader._DocxDocument")
    def test_read_empty_document_returns_empty_string(
        self,
        mock_docx_document: MagicMock,
    ) -> None:
        path = Path("/tmp/empty.docx")
        mock_document = MagicMock()
        mock_document.paragraphs = []
        mock_docx_document.return_value = mock_document

        result = DocxReader().read(path)

        self.assertEqual(result, "")

    @patch("app.content.docx_reader._DocxDocument")
    def test_read_skips_empty_paragraphs(self, mock_docx_document: MagicMock) -> None:
        path = Path("/tmp/course.docx")
        mock_document = MagicMock()
        mock_document.paragraphs = [
            _make_paragraph("First"),
            _make_paragraph(""),
            _make_paragraph("Second"),
        ]
        mock_docx_document.return_value = mock_document

        result = DocxReader().read(path)

        self.assertEqual(result, "First\nSecond")

    @patch("app.content.docx_reader._DocxDocument")
    def test_library_exception_propagates(self, mock_docx_document: MagicMock) -> None:
        path = Path("/tmp/broken.docx")
        mock_docx_document.side_effect = RuntimeError("invalid DOCX")

        with self.assertRaises(RuntimeError):
            DocxReader().read(path)


if __name__ == "__main__":
    unittest.main()
