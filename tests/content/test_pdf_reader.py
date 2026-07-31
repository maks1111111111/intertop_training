"""Tests for PDF text extraction (``app.content.pdf_reader``)."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from app.content.pdf_reader import PdfReader


def _make_page(text: Optional[str]) -> MagicMock:
    page = MagicMock()
    page.extract_text.return_value = text
    return page


class PdfReaderReadTests(unittest.TestCase):
    """Tests for :meth:`PdfReader.read`."""

    @patch("app.content.pdf_reader._PypdfReader")
    def test_read_single_page(self, mock_pypdf_reader: MagicMock) -> None:
        path = Path("/tmp/course.pdf")
        mock_reader = MagicMock()
        mock_reader.pages = [_make_page("Hello World")]
        mock_pypdf_reader.return_value = mock_reader

        result = PdfReader().read(path)

        self.assertEqual(result, "Hello World")
        mock_pypdf_reader.assert_called_once_with(str(path))

    @patch("app.content.pdf_reader._PypdfReader")
    def test_read_multiple_pages(self, mock_pypdf_reader: MagicMock) -> None:
        path = Path("/tmp/course.pdf")
        mock_reader = MagicMock()
        mock_reader.pages = [_make_page("Page 1"), _make_page("Page 2")]
        mock_pypdf_reader.return_value = mock_reader

        result = PdfReader().read(path)

        self.assertEqual(result, "Page 1\nPage 2")

    @patch("app.content.pdf_reader._PypdfReader")
    def test_read_empty_text_returns_empty_string(
        self,
        mock_pypdf_reader: MagicMock,
    ) -> None:
        path = Path("/tmp/empty.pdf")
        mock_reader = MagicMock()
        mock_reader.pages = [_make_page(None)]
        mock_pypdf_reader.return_value = mock_reader

        result = PdfReader().read(path)

        self.assertEqual(result, "")

    @patch("app.content.pdf_reader._PypdfReader")
    def test_library_exception_propagates(self, mock_pypdf_reader: MagicMock) -> None:
        path = Path("/tmp/broken.pdf")
        mock_pypdf_reader.side_effect = RuntimeError("invalid PDF")

        with self.assertRaises(RuntimeError):
            PdfReader().read(path)


if __name__ == "__main__":
    unittest.main()
