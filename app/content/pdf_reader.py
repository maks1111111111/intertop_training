"""PDF text extraction for the Content Engine import pipeline."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader as _PypdfReader


class PdfReader:
    """Extract plain text from PDF files."""

    def read(self, path: Path) -> str:
        """Read and extract text from all pages of a PDF file.

        Args:
            path: Path to the PDF file.

        Returns:
            Extracted text with pages joined by newlines, or an empty string
            when no text is available.
        """
        reader = _PypdfReader(str(path))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text)
