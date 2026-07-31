"""Import session models for the course import pipeline.

An :class:`ImportSession` groups one or more source documents and their
extracted text for a single course-import operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.content.importer import ImportSource


@dataclass(frozen=True)
class ImportDocument:
    """A source document and its extracted text within an import session."""

    source: ImportSource
    text: str


@dataclass
class ImportSession:
    """Describes a single course import operation."""

    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    documents: list[ImportDocument] = field(default_factory=list)

    def add_document(self, source: ImportSource, text: str) -> None:
        """Append a document with extracted text to the session."""
        self.documents.append(ImportDocument(source=source, text=text))

    def document_count(self) -> int:
        """Return the number of documents in the session."""
        return len(self.documents)
