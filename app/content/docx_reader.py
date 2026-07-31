"""DOCX text extraction for the Content Engine import pipeline."""

from __future__ import annotations

from pathlib import Path

from docx import Document as _DocxDocument


class DocxReader:
    """Extract plain text from DOCX files."""

    def read(self, path: Path) -> str:
        """Read and extract text from all paragraphs of a DOCX file.

        Args:
            path: Path to the DOCX file.

        Returns:
            Extracted text with non-empty paragraphs joined by newlines, or
            an empty string when no text is available.
        """
        document = _DocxDocument(str(path))
        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text
        ]
        return "\n".join(paragraphs)
