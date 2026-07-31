"""Tests for import session models (``app.content.import_session``)."""

from __future__ import annotations

import unittest
from datetime import timezone
from pathlib import Path
from uuid import UUID

from app.content.import_session import ImportDocument, ImportSession
from app.content.importer import ImportSource


class ImportSessionTests(unittest.TestCase):
    """Tests for :class:`ImportSession`."""

    def test_new_session_is_empty(self) -> None:
        session = ImportSession()

        self.assertEqual(session.document_count(), 0)
        self.assertEqual(session.documents, [])

    def test_add_document(self) -> None:
        session = ImportSession()
        source = ImportSource(path=Path("/tmp/lesson.pdf"), source_type="pdf")

        session.add_document(source, "Extracted lesson text.")

        self.assertEqual(session.document_count(), 1)
        self.assertEqual(
            session.documents[0],
            ImportDocument(source=source, text="Extracted lesson text."),
        )

    def test_document_count(self) -> None:
        session = ImportSession()
        pdf_source = ImportSource(path=Path("/tmp/a.pdf"), source_type="pdf")
        docx_source = ImportSource(path=Path("/tmp/b.docx"), source_type="docx")

        session.add_document(pdf_source, "First document.")
        session.add_document(docx_source, "Second document.")

        self.assertEqual(session.document_count(), 2)

    def test_session_id_is_uuid(self) -> None:
        session = ImportSession()

        self.assertIsInstance(session.id, UUID)

    def test_created_at_is_timezone_aware(self) -> None:
        session = ImportSession()

        self.assertIsNotNone(session.created_at.tzinfo)
        self.assertEqual(session.created_at.tzinfo, timezone.utc)
