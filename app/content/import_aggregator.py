"""Import session aggregation for the course import pipeline.

Combines extracted text from all documents in an :class:`ImportSession`
into a single course-level text block.
"""

from __future__ import annotations

from app.content.import_session import ImportSession


class ImportAggregator:
    """Merge import session documents into one aggregated text."""

    def aggregate(self, session: ImportSession) -> str:
        """Combine non-empty document texts in insertion order.

        Args:
            session: Import session whose documents should be merged.

        Returns:
            Aggregated text with documents separated by blank lines, or an
            empty string when the session has no documents or all documents
            are empty.
        """
        parts = [document.text for document in session.documents if document.text]
        return "\n\n".join(parts)
