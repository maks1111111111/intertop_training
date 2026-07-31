"""Tests for PPTX text extraction (``app.content.pptx_reader``)."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from app.content.pptx_reader import PptxReader


def _make_shape(text: Optional[str]) -> object:
    if text is None:
        return object()
    shape = MagicMock()
    shape.text = text
    return shape


def _make_slide(shapes: list[object]) -> MagicMock:
    slide = MagicMock()
    slide.shapes = shapes
    return slide


class PptxReaderReadTests(unittest.TestCase):
    """Tests for :meth:`PptxReader.read`."""

    @patch("app.content.pptx_reader._PptxPresentation")
    def test_read_single_slide(self, mock_pptx_presentation: MagicMock) -> None:
        path = Path("/tmp/course.pptx")
        mock_presentation = MagicMock()
        mock_presentation.slides = [_make_slide([_make_shape("Hello World")])]
        mock_pptx_presentation.return_value = mock_presentation

        result = PptxReader().read(path)

        self.assertEqual(result, "Hello World")
        mock_pptx_presentation.assert_called_once_with(str(path))

    @patch("app.content.pptx_reader._PptxPresentation")
    def test_read_multiple_slides(self, mock_pptx_presentation: MagicMock) -> None:
        path = Path("/tmp/course.pptx")
        mock_presentation = MagicMock()
        mock_presentation.slides = [
            _make_slide([_make_shape("Slide 1")]),
            _make_slide([_make_shape("Slide 2")]),
        ]
        mock_pptx_presentation.return_value = mock_presentation

        result = PptxReader().read(path)

        self.assertEqual(result, "Slide 1\nSlide 2")

    @patch("app.content.pptx_reader._PptxPresentation")
    def test_read_skips_shapes_without_text(
        self,
        mock_pptx_presentation: MagicMock,
    ) -> None:
        path = Path("/tmp/course.pptx")
        mock_presentation = MagicMock()
        mock_presentation.slides = [
            _make_slide([_make_shape("Visible text"), _make_shape(None)]),
        ]
        mock_pptx_presentation.return_value = mock_presentation

        result = PptxReader().read(path)

        self.assertEqual(result, "Visible text")

    @patch("app.content.pptx_reader._PptxPresentation")
    def test_read_empty_presentation_returns_empty_string(
        self,
        mock_pptx_presentation: MagicMock,
    ) -> None:
        path = Path("/tmp/empty.pptx")
        mock_presentation = MagicMock()
        mock_presentation.slides = []
        mock_pptx_presentation.return_value = mock_presentation

        result = PptxReader().read(path)

        self.assertEqual(result, "")

    @patch("app.content.pptx_reader._PptxPresentation")
    def test_read_skips_empty_text(self, mock_pptx_presentation: MagicMock) -> None:
        path = Path("/tmp/course.pptx")
        mock_presentation = MagicMock()
        mock_presentation.slides = [
            _make_slide([_make_shape("First"), _make_shape("")]),
        ]
        mock_pptx_presentation.return_value = mock_presentation

        result = PptxReader().read(path)

        self.assertEqual(result, "First")

    @patch("app.content.pptx_reader._PptxPresentation")
    def test_library_exception_propagates(
        self,
        mock_pptx_presentation: MagicMock,
    ) -> None:
        path = Path("/tmp/broken.pptx")
        mock_pptx_presentation.side_effect = RuntimeError("invalid PPTX")

        with self.assertRaises(RuntimeError):
            PptxReader().read(path)


if __name__ == "__main__":
    unittest.main()
