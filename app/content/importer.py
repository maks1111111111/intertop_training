"""Course import pipeline foundation for the Content Engine.

Detects supported source file types and prepares import metadata.
No file reading, AI processing, or course creation is performed yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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


class CourseImporter:
    """Foundation for the course import pipeline."""

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
