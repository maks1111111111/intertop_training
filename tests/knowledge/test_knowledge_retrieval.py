"""Tests for knowledge chunk lexical retrieval."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import List, Sequence

from app.database.db import initialize_database
from app.knowledge.models import KnowledgeDocumentChunk, KnowledgeDocumentChunkInput
from app.knowledge.retrieval import (
    KnowledgeChunkRetrievalService,
    KnowledgeRetrievalError,
    rank_chunks,
    score_chunk,
    tokenize,
    unique_query_terms,
)
from app.repositories import knowledge_chunk_repository, knowledge_document_repository


class KnowledgeRetrievalHelpersTests(unittest.TestCase):
    def test_tokenize_case_insensitive(self) -> None:
        self.assertEqual(
            tokenize("Return Policy"),
            tokenize("return policy"),
        )

    def test_tokenize_strips_punctuation(self) -> None:
        self.assertIn("policy", tokenize("return-policy, effective!"))
        self.assertIn("return", tokenize("return-policy, effective!"))

    def test_unique_query_terms_deduplicates_repeated_terms(self) -> None:
        self.assertEqual(
            unique_query_terms("return return policy"),
            ("return", "policy"),
        )

    def test_score_chunk_zero_for_no_overlap(self) -> None:
        self.assertEqual(score_chunk(("alpha",), "unrelated beta text"), 0.0)

    def test_score_chunk_full_coverage(self) -> None:
        self.assertEqual(
            score_chunk(("return", "policy"), "Company return policy details"),
            1.0,
        )


class KnowledgeChunkRetrievalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = KnowledgeChunkRetrievalService()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_document(
        self,
        *,
        company_id: str,
        title: str,
        filename: str,
    ) -> str:
        document = knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=filename,
            source_type="pdf",
        )
        return document.document_id

    def _replace_chunks(
        self,
        *,
        company_id: str,
        document_id: str,
        chunks: List[KnowledgeDocumentChunkInput],
    ) -> None:
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=company_id,
            document_id=document_id,
            chunks=chunks,
        )

    def _chunk_input(
        self,
        *,
        chunk_index: int,
        text: str,
        start_char: int = 0,
        end_char: int = 10,
    ) -> KnowledgeDocumentChunkInput:
        return KnowledgeDocumentChunkInput(
            chunk_index=chunk_index,
            text=text,
            start_char=start_char,
            end_char=end_char,
        )

    def test_exact_keyword_match(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="General onboarding information.",
                ),
                self._chunk_input(
                    chunk_index=1,
                    text="Return policy applies within 14 days.",
                    start_char=20,
                    end_char=40,
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(len(results), 1)
        self.assertIn("Return policy", results[0].chunk.text)
        self.assertGreater(results[0].score, 0.0)

    def test_multiple_matching_terms_rank_higher(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Return information only."),
                self._chunk_input(
                    chunk_index=1,
                    text="Return policy for defective items.",
                    start_char=20,
                    end_char=40,
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=2,
        )

        self.assertEqual(len(results), 2)
        self.assertGreater(results[0].score, results[1].score)
        self.assertIn("policy", results[0].chunk.text.casefold())

    def test_irrelevant_chunks_excluded(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Warehouse logistics schedule."),
                self._chunk_input(
                    chunk_index=1,
                    text="Employee vacation planning.",
                    start_char=20,
                    end_char=40,
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(results, ())

    def test_case_insensitive_search(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="RETURN POLICY details."),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(len(results), 1)

    def test_punctuation_normalization(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="Return-policy: effective immediately!",
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(len(results), 1)

    def test_russian_text(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Политика",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="Политика возврата товара действует 14 дней.",
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="политика возврата",
        )

        self.assertEqual(len(results), 1)
        self.assertIn("возврата", results[0].chunk.text)

    def test_kazakh_unicode_text(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Саясат",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="Қайтару саясаты 14 күнге дейін қолданылады.",
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="қайтару саясаты",
        )

        self.assertEqual(len(results), 1)
        self.assertIn("Қайтару", results[0].chunk.text)

    def test_english_text(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Manual",
            filename="manual.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="Customer support escalation workflow.",
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="customer support",
        )

        self.assertEqual(len(results), 1)

    def test_tenant_isolation(self) -> None:
        document_a = self._create_document(
            company_id="company-a",
            title="A",
            filename="a.pdf",
        )
        document_b = self._create_document(
            company_id="company-b",
            title="B",
            filename="b.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_a,
            chunks=[
                self._chunk_input(chunk_index=0, text="Return policy for company A."),
            ],
        )
        self._replace_chunks(
            company_id="company-b",
            document_id=document_b,
            chunks=[
                self._chunk_input(chunk_index=0, text="Return policy for company B."),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.company_id, "company-a")
        self.assertEqual(results[0].chunk.document_id, document_a)

    def test_same_document_id_in_different_companies_do_not_cross_contaminate(
        self,
    ) -> None:
        shared_document_id = "doc-shared-id"
        for company_id, text in (
            ("company-a", "Alpha secret keyword"),
            ("company-b", "Beta secret keyword"),
        ):
            knowledge_document_repository.create_document(
                self.db_path,
                company_id=company_id,
                title="Shared",
                original_filename="shared.pdf",
                source_type="pdf",
            )
            documents = knowledge_document_repository.list_for_company(
                self.db_path,
                company_id=company_id,
            )
            document_id = documents[0].document_id
            self._replace_chunks(
                company_id=company_id,
                document_id=document_id,
                chunks=[self._chunk_input(chunk_index=0, text=text)],
            )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="alpha secret",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.company_id, "company-a")
        self.assertIn("Alpha", results[0].chunk.text)

    def test_deterministic_ordering(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Return policy section one."),
                self._chunk_input(
                    chunk_index=1,
                    text="Return policy section two.",
                    start_char=20,
                    end_char=40,
                ),
            ],
        )

        first = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=2,
        )
        second = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=2,
        )

        self.assertEqual(first, second)

    def test_limit_respected(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Return policy one."),
                self._chunk_input(
                    chunk_index=1,
                    text="Return policy two.",
                    start_char=10,
                    end_char=20,
                ),
                self._chunk_input(
                    chunk_index=2,
                    text="Return policy three.",
                    start_char=20,
                    end_char=30,
                ),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=2,
        )

        self.assertEqual(len(results), 2)

    def test_empty_query_rejected(self) -> None:
        with self.assertRaises(KnowledgeRetrievalError) as ctx:
            self.service.search(
                self.db_path,
                company_id="company-a",
                query="   ",
            )
        self.assertEqual(ctx.exception.message, "query must not be empty")

    def test_empty_company_id_rejected(self) -> None:
        with self.assertRaises(KnowledgeRetrievalError) as ctx:
            self.service.search(
                self.db_path,
                company_id="  ",
                query="policy",
            )
        self.assertEqual(ctx.exception.message, "company_id must not be empty")

    def test_zero_limit_rejected(self) -> None:
        with self.assertRaises(KnowledgeRetrievalError) as ctx:
            self.service.search(
                self.db_path,
                company_id="company-a",
                query="policy",
                limit=0,
            )
        self.assertEqual(ctx.exception.message, "limit must be positive")

    def test_negative_limit_rejected(self) -> None:
        with self.assertRaises(KnowledgeRetrievalError) as ctx:
            self.service.search(
                self.db_path,
                company_id="company-a",
                query="policy",
                limit=-1,
            )
        self.assertEqual(ctx.exception.message, "limit must be positive")

    def test_no_matches_returns_empty_tuple(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Unrelated warehouse content."),
            ],
        )

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="nonexistent topic",
        )

        self.assertEqual(results, ())

    def test_repeated_query_term_does_not_distort_score(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="Return policy details."),
            ],
        )

        single = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=1,
        )[0].score
        repeated = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return return policy policy",
            limit=1,
        )[0].score

        self.assertEqual(single, repeated)

    def test_stored_chunk_model_returned_intact(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(
                    chunk_index=0,
                    text="Return policy details.",
                    start_char=5,
                    end_char=25,
                ),
            ],
        )
        stored = knowledge_chunk_repository.list_for_document(
            self.db_path,
            company_id="company-a",
            document_id=document_id,
        )[0]

        results = self.service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
            limit=1,
        )

        self.assertEqual(results[0].chunk, stored)

    def test_list_for_company_repository_helper(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                self._chunk_input(chunk_index=0, text="First chunk."),
                self._chunk_input(
                    chunk_index=1,
                    text="Second chunk.",
                    start_char=10,
                    end_char=20,
                ),
            ],
        )

        chunks = knowledge_chunk_repository.list_for_company(
            self.db_path,
            company_id="company-a",
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[1].chunk_index, 1)

    def test_rank_chunks_stable_tie_breaker(self) -> None:
        chunks = (
            KnowledgeDocumentChunk(
                id=2,
                company_id="company-a",
                document_id="doc-1",
                chunk_index=1,
                text="return policy",
                start_char=0,
                end_char=13,
                created_at="2026-01-01",
            ),
            KnowledgeDocumentChunk(
                id=1,
                company_id="company-a",
                document_id="doc-1",
                chunk_index=0,
                text="return policy",
                start_char=0,
                end_char=13,
                created_at="2026-01-01",
            ),
        )

        ranked = rank_chunks("return policy", chunks)

        self.assertEqual(ranked[0].chunk.chunk_index, 0)
        self.assertEqual(ranked[1].chunk.chunk_index, 1)

    def test_injected_chunk_loader_is_used(self) -> None:
        captured: dict[str, str] = {}

        def loader(db_path: Path, company_id: str) -> Sequence[KnowledgeDocumentChunk]:
            captured["db_path"] = str(db_path)
            captured["company_id"] = company_id
            return (
                KnowledgeDocumentChunk(
                    id=1,
                    company_id=company_id,
                    document_id="doc-1",
                    chunk_index=0,
                    text="Injected return policy chunk.",
                    start_char=0,
                    end_char=20,
                    created_at="2026-01-01",
                ),
            )

        service = KnowledgeChunkRetrievalService(chunk_loader=loader)
        results = service.search(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(captured["company_id"], "company-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.text, "Injected return policy chunk.")


if __name__ == "__main__":
    unittest.main()
