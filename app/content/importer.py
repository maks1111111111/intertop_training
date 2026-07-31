"""Course import pipeline foundation for the Content Engine.

Detects supported source file types, routes them to registered readers,
and prepares import metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.content.import_readers import ImportReader
from app.content.pdf_reader import PdfReader

_SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".mp4": "mp4",
}


@dataclass(frozen=True)
class ImportSource:
    """Description of a course import source file."""

    path: Path
    source_type: str


@dataclass(frozen=True)
class ImportResult:
    """Prepared import metadata for a detected source file."""

    source: ImportSource
    imported_at: datetime


def _default_readers() -> dict[str, ImportReader]:
    return {
        "pdf": PdfReader(),
    }


class CourseImporter:
    """Foundation for the course import pipeline."""

    def __init__(self, readers: Optional[dict[str, ImportReader]] = None) -> None:
        self._readers = readers if readers is not None else _default_readers()

    def detect_source(self, path: Path) -> ImportSource:
        """Detect the import source type from the file extension.

        Args:
            path: Path to the source file.

        Returns:
            An :class:`ImportSource` describing the file and its type.

        Raises:
            ValueError: If the file extension is not supported.
        """
        extension = path.suffix.lower()
        source_type = _SUPPORTED_EXTENSIONS.get(extension)
        if source_type is None:
            raise ValueError(
                f"Unsupported import source format: {extension or '(no extension)'}"
            )
        return ImportSource(path=path, source_type=source_type)

    def prepare_import(self, path: Path) -> ImportResult:
        """Prepare import metadata for a source file.

        Args:
            path: Path to the source file.

        Returns:
            An :class:`ImportResult` with detected source and timestamp.

        Raises:
            ValueError: If the file extension is not supported.
        """
        source = self.detect_source(path)
        return ImportResult(
            source=source,
            imported_at=datetime.now(timezone.utc),
        )

    def read_source(self, path: Path) -> str:
        """Detect the source type and extract text using a registered reader.

        Args:
            path: Path to the source file.

        Returns:
            Extracted text from the source file.

        Raises:
            ValueError: If the file extension is not supported or no reader
                is registered for the detected source type.
        """
        source = self.detect_source(path)
        reader = self._readers.get(source.source_type)
        if reader is None:
            raise ValueError(
                f"No reader registered for source type: {source.source_type}"
            )
        return reader.read(path)
