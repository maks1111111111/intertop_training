"""Tests for import session aggregation (``app.content.import_aggregator``)."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.content.import_aggregator import ImportAggregator
from app.content.import_session import ImportSession
from app.content.importer import ImportSource


class ImportAggregatorTests(unittest.TestCase):
    """Tests for :class:`ImportAggregator`."""

    def setUp(self) -> None:
        self.aggregator = ImportAggregator()

    def test_empty_session(self) -> None:
        session = ImportSession()

        self.assertEqual(self.aggregator.aggregate(session), "")

    def test_single_document(self) -> None:
        session = ImportSession()
        source = ImportSource(path=Path("/tmp/lesson.pdf"), source_type="pdf")
        session.add_document(source, "Single document text.")

        self.assertEqual(
            self.aggregator.aggregate(session),
            "Single document text.",
        )

    def test_multiple_documents(self) -> None:
        session = ImportSession()
        pdf_source = ImportSource(path=Path("/tmp/a.pdf"), source_type="pdf")
        docx_source = ImportSource(path=Path("/tmp/b.docx"), source_type="docx")
        session.add_document(pdf_source, "First document.")
        session.add_document(docx_source, "Second document.")

        self.assertEqual(
            self.aggregator.aggregate(session),
            "First document.\n\nSecond document.",
        )

    def test_empty_documents_are_skipped(self) -> None:
        session = ImportSession()
        pdf_source = ImportSource(path=Path("/tmp/a.pdf"), source_type="pdf")
        docx_source = ImportSource(path=Path("/tmp/b.docx"), source_type="docx")
        pptx_source = ImportSource(path=Path("/tmp/c.pptx"), source_type="pptx")
        session.add_document(pdf_source, "")
        session.add_document(docx_source, "Only non-empty text.")
        session.add_document(pptx_source, "")

        self.assertEqual(
            self.aggregator.aggregate(session),
            "Only non-empty text.",
        )

    def test_all_documents_empty(self) -> None:
        session = ImportSession()
        pdf_source = ImportSource(path=Path("/tmp/a.pdf"), source_type="pdf")
        docx_source = ImportSource(path=Path("/tmp/b.docx"), source_type="docx")
        session.add_document(pdf_source, "")
        session.add_document(docx_source, "")

        self.assertEqual(self.aggregator.aggregate(session), "")

    def test_document_order_is_preserved(self) -> None:
        session = ImportSession()
        sources = [
            ImportSource(path=Path("/tmp/a.pdf"), source_type="pdf"),
            ImportSource(path=Path("/tmp/b.docx"), source_type="docx"),
            ImportSource(path=Path("/tmp/c.pptx"), source_type="pptx"),
        ]
        session.add_document(sources[0], "Alpha.")
        session.add_document(sources[1], "Beta.")
        session.add_document(sources[2], "Gamma.")

        self.assertEqual(
            self.aggregator.aggregate(session),
            "Alpha.\n\nBeta.\n\nGamma.",
        )
