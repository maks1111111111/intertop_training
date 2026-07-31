"""Import reader protocol for the Content Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ImportReader(Protocol):
    """Protocol for extracting text from import source files."""

    def read(self, path: Path) -> str:
        """Read and extract text from the source file."""
        ...
