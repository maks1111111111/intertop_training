"""Tests for knowledge_chunk_repository."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional

from app.database.db import get_connection, initialize_database
from app.knowledge.chunking import KnowledgeChunk, KnowledgeTextChunker
from app.knowledge.models import KnowledgeDocumentChunkInput
from app.repositories import knowledge_chunk_repository, knowledge_document_repository


class KnowledgeChunkRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.document = knowledge_document_repository.create_document(
            self.db_path,
            company_id="company-a",
            title="Policy Manual",
            original_filename="policy.pdf",
            source_type="pdf",
            extracted_text="Sample extracted text for chunking.",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _chunk_input(
        self,
        *,
        chunk_index: int = 0,
        text: str = "Chunk text",
        start_char: int = 0,
        end_char: int = 10,
    ) -> KnowledgeDocumentChunkInput:
        return KnowledgeDocumentChunkInput(
            chunk_index=chunk_index,
            text=text,
            start_char=start_char,
            end_char=end_char,
        )

    def _replace(
        self,
        *,
        company_id: str = "company-a",
        document_id: Optional[str] = None,
        chunks: Optional[List] = None,
    ) -> int:
        return knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=company_id,
            document_id=document_id or self.document.document_id,
            chunks=[self._chunk_input()] if chunks is None else chunks,
        )

    def test_replace_persists_chunks(self) -> None:
        count = self._replace(
            chunks=[
                self._chunk_input(chunk_index=0, text="First"),
                self._chunk_input(
                    chunk_index=1,
                    text="Second",
                    start_char=10,
                    end_char=20,
                ),
            ]
        )

        self.assertEqual(count, 2)
        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )
        self.assertEqual(len(stored), 2)
        self.assertEqual(stored[0].chunk_index, 0)
        self.assertEqual(stored[0].text, "First")
        self.assertEqual(stored[1].chunk_index, 1)
        self.assertEqual(stored[1].text, "Second")

    def test_replace_accepts_knowledge_chunk_objects(self) -> None:
        chunker = KnowledgeTextChunker()
        generated = chunker.chunk("Paragraph one.\n\nParagraph two.")
        self.assertGreater(len(generated), 0)

        count = knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
            chunks=generated,
        )

        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )
        self.assertEqual(count, len(generated))
        self.assertEqual(len(stored), len(generated))
        for source, persisted in zip(generated, stored):
            self.assertEqual(source.index, persisted.chunk_index)
            self.assertEqual(source.text, persisted.text)
            self.assertEqual(source.start_char, persisted.start_char)
            self.assertEqual(source.end_char, persisted.end_char)

    def test_list_for_document_ordered_by_chunk_index(self) -> None:
        self._replace(
            chunks=[
                self._chunk_input(chunk_index=2, text="Third"),
                self._chunk_input(chunk_index=0, text="First"),
                self._chunk_input(chunk_index=1, text="Second"),
            ]
        )

        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )

        self.assertEqual([chunk.chunk_index for chunk in stored], [0, 1, 2])
        self.assertEqual([chunk.text for chunk in stored], ["First", "Second", "Third"])

    def test_count_for_document(self) -> None:
        self.assertEqual(
            knowledge_chunk_repository.count_for_document(
                self.db_path,
                company_id="company-a",
                document_id=self.document.document_id,
            ),
            0,
        )

        self._replace(
            chunks=[
                self._chunk_input(chunk_index=0, text="One"),
                self._chunk_input(
                    chunk_index=1,
                    text="Two",
                    start_char=3,
                    end_char=6,
                ),
            ]
        )

        self.assertEqual(
            knowledge_chunk_repository.count_for_document(
                self.db_path,
                company_id="company-a",
                document_id=self.document.document_id,
            ),
            2,
        )

    def test_delete_for_document(self) -> None:
        self._replace()
        deleted = knowledge_chunk_repository.delete_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )

        self.assertEqual(deleted, 1)
        self.assertEqual(
            knowledge_chunk_repository.count_for_document(
                self.db_path,
                company_id="company-a",
                document_id=self.document.document_id,
            ),
            0,
        )

    def test_replace_is_atomic_and_replaces_existing_chunks(self) -> None:
        self._replace(
            chunks=[
                self._chunk_input(chunk_index=0, text="Original"),
                self._chunk_input(
                    chunk_index=1,
                    text="Original second",
                    start_char=5,
                    end_char=10,
                ),
            ]
        )

        self._replace(
            chunks=[
                self._chunk_input(chunk_index=0, text="Replacement"),
            ]
        )

        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].text, "Replacement")

    def test_replace_with_empty_sequence_deletes_existing_chunks(self) -> None:
        self._replace()
        count = self._replace(chunks=[])

        self.assertEqual(count, 0)
        self.assertEqual(
            knowledge_chunk_repository.count_for_document(
                self.db_path,
                company_id="company-a",
                document_id=self.document.document_id,
            ),
            0,
        )

    def test_validation_failure_does_not_delete_existing_chunks(self) -> None:
        self._replace(
            chunks=[
                self._chunk_input(chunk_index=0, text="Keep me"),
            ]
        )

        with self.assertRaises(ValueError):
            self._replace(
                chunks=[
                    self._chunk_input(chunk_index=0, text="   "),
                ]
            )

        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].text, "Keep me")

    def test_duplicate_chunk_index_rejected_before_mutation(self) -> None:
        self._replace(
            chunks=[
                self._chunk_input(chunk_index=0, text="Existing"),
            ]
        )

        with self.assertRaises(ValueError):
            self._replace(
                chunks=[
                    self._chunk_input(chunk_index=0, text="First"),
                    self._chunk_input(
                        chunk_index=0,
                        text="Duplicate",
                        start_char=5,
                        end_char=10,
                    ),
                ]
            )

        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].text, "Existing")

    def test_empty_text_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._replace(chunks=[self._chunk_input(text="   ")])

    def test_invalid_offsets_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._replace(
                chunks=[self._chunk_input(start_char=5, end_char=5)]
            )

        with self.assertRaises(ValueError):
            self._replace(
                chunks=[self._chunk_input(start_char=-1, end_char=3)]
            )

    def test_negative_chunk_index_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._replace(chunks=[self._chunk_input(chunk_index=-1)])

    def test_empty_company_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._replace(company_id="  ")

    def test_empty_document_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            knowledge_chunk_repository.replace_document_chunks(
                self.db_path,
                company_id="company-a",
                document_id="",
                chunks=[self._chunk_input()],
            )

    def test_tenant_isolation_for_list(self) -> None:
        other_document = knowledge_document_repository.create_document(
            self.db_path,
            company_id="company-b",
            title="Other Manual",
            original_filename="other.pdf",
            source_type="pdf",
        )
        self._replace(
            chunks=[self._chunk_input(chunk_index=0, text="Company A chunk")],
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id="company-b",
            document_id=other_document.document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Company B chunk"),
            ],
        )

        company_a_chunks = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )
        company_b_chunks = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-b",
            document_id=other_document.document_id,
        )

        self.assertEqual(len(company_a_chunks), 1)
        self.assertEqual(company_a_chunks[0].text, "Company A chunk")
        self.assertEqual(len(company_b_chunks), 1)
        self.assertEqual(company_b_chunks[0].text, "Company B chunk")

    def test_same_document_id_for_different_companies_isolated(self) -> None:
        shared_document_id = self.document.document_id
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id="company-b",
            document_id=shared_document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Other tenant chunk"),
            ],
        )
        self._replace(
            chunks=[self._chunk_input(chunk_index=0, text="Primary tenant chunk")],
        )

        primary_count = knowledge_chunk_repository.count_for_document(
            self.db_path,
            company_id="company-a",
            document_id=shared_document_id,
        )
        other_count = knowledge_chunk_repository.count_for_document(
            self.db_path,
            company_id="company-b",
            document_id=shared_document_id,
        )

        self.assertEqual(primary_count, 1)
        self.assertEqual(other_count, 1)

    def test_delete_for_document_only_affects_matching_tenant(self) -> None:
        other_document = knowledge_document_repository.create_document(
            self.db_path,
            company_id="company-b",
            title="Other Manual",
            original_filename="other.pdf",
            source_type="pdf",
        )
        self._replace(
            chunks=[self._chunk_input(chunk_index=0, text="Keep in A")],
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id="company-b",
            document_id=other_document.document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Delete in B"),
            ],
        )

        deleted = knowledge_chunk_repository.delete_for_document(
            self.db_path,
            company_id="company-b",
            document_id=other_document.document_id,
        )

        self.assertEqual(deleted, 1)
        self.assertEqual(
            knowledge_chunk_repository.count_for_document(
                self.db_path,
                company_id="company-a",
                document_id=self.document.document_id,
            ),
            1,
        )

    def test_replace_deletes_only_matching_company_document(self) -> None:
        other_document = knowledge_document_repository.create_document(
            self.db_path,
            company_id="company-b",
            title="Other Manual",
            original_filename="other.pdf",
            source_type="pdf",
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id="company-b",
            document_id=other_document.document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Other doc chunk"),
            ],
        )
        self._replace(
            chunks=[self._chunk_input(chunk_index=0, text="Primary doc chunk")],
        )

        stored_other = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-b",
            document_id=other_document.document_id,
        )
        self.assertEqual(len(stored_other), 1)
        self.assertEqual(stored_other[0].text, "Other doc chunk")

    def test_persisted_model_fields(self) -> None:
        self._replace(
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="Persisted chunk",
                    start_char=3,
                    end_char=18,
                )
            ]
        )

        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=self.document.document_id,
        )[0]

        self.assertIsInstance(stored.id, int)
        self.assertEqual(stored.company_id, "company-a")
        self.assertEqual(stored.document_id, self.document.document_id)
        self.assertEqual(stored.chunk_index, 0)
        self.assertEqual(stored.text, "Persisted chunk")
        self.assertEqual(stored.start_char, 3)
        self.assertEqual(stored.end_char, 18)
        self.assertTrue(stored.created_at)

    def test_initialize_database_still_works(self) -> None:
        db_path = Path(self._tmpdir.name) / "fresh.db"
        initialize_database(db_path)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'knowledge_document_chunks'
                """
            ).fetchone()

        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
