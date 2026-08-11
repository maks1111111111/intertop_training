"""Tests for KnowledgeRetrievalContextService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional, Sequence

from app.database.db import initialize_database
from app.knowledge.context_builder import (
    DEFAULT_MAX_SOURCES,
    KnowledgeContextBuildingError,
    KnowledgeContextBuildingOptions,
    KnowledgeRetrievalContext,
    KnowledgeRetrievalContextBuilder,
)
from app.knowledge.context_service import KnowledgeRetrievalContextService
from app.knowledge.models import KnowledgeDocumentChunkInput
from app.knowledge.retrieval import (
    KnowledgeChunkRetrievalService,
    KnowledgeRetrievalError,
    KnowledgeRetrievalResult,
)
from app.repositories import knowledge_chunk_repository, knowledge_document_repository


def _chunk_input(
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


class _RecordingRetrievalService:
    """Stub retrieval service that records calls and returns preset results."""

    def __init__(
        self,
        results: Sequence[KnowledgeRetrievalResult] = (),
        error: Optional[Exception] = None,
    ) -> None:
        self.results = tuple(results)
        self.error = error
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        db_path: Path,
        *,
        company_id: str,
        query: str,
        limit: int = 5,
    ) -> tuple[KnowledgeRetrievalResult, ...]:
        self.calls.append(
            {
                "db_path": db_path,
                "company_id": company_id,
                "query": query,
                "limit": limit,
            }
        )
        if self.error is not None:
            raise self.error
        return self.results


class _RecordingContextBuilder:
    """Stub context builder that records calls and returns a preset context."""

    def __init__(
        self,
        context: Optional[KnowledgeRetrievalContext] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.context = context
        self.error = error
        self.calls: list[dict[str, object]] = []

    def build(
        self,
        *,
        company_id: str,
        query: str,
        results: Sequence[KnowledgeRetrievalResult],
        options: Optional[KnowledgeContextBuildingOptions] = None,
    ) -> KnowledgeRetrievalContext:
        self.calls.append(
            {
                "company_id": company_id,
                "query": query,
                "results": tuple(results),
                "options": options,
            }
        )
        if self.error is not None:
            raise self.error
        if self.context is not None:
            return self.context
        return KnowledgeRetrievalContextBuilder().build(
            company_id=company_id,
            query=query,
            results=results,
            options=options,
        )


class KnowledgeRetrievalContextServiceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.service = KnowledgeRetrievalContextService()

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
        chunks: Sequence[KnowledgeDocumentChunkInput],
    ) -> None:
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=company_id,
            document_id=document_id,
            chunks=chunks,
        )

    def test_one_matching_chunk_produces_context(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                _chunk_input(
                    chunk_index=0,
                    text="Return policy for employees.",
                    end_char=28,
                ),
            ],
        )

        context = self.service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(context.source_count, 1)
        self.assertIn("Return policy", context.context_text)
        self.assertEqual(context.query, "return policy")

    def test_multiple_matching_chunks_preserve_ranking(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Handbook",
            filename="handbook.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                _chunk_input(
                    chunk_index=0,
                    text="General onboarding overview.",
                    end_char=30,
                ),
                _chunk_input(
                    chunk_index=1,
                    text="Return policy and refund rules.",
                    start_char=30,
                    end_char=62,
                ),
                _chunk_input(
                    chunk_index=2,
                    text="Return policy details for managers.",
                    start_char=62,
                    end_char=98,
                ),
            ],
        )

        context = self.service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
            retrieval_limit=3,
        )

        self.assertGreaterEqual(context.source_count, 2)
        self.assertGreaterEqual(
            context.sources[0].chunk_index,
            0,
        )
        policy_indexes = [source.chunk_index for source in context.sources]
        self.assertIn(1, policy_indexes)
        self.assertIn(2, policy_indexes)

    def test_no_matches_returns_empty_context(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Policy",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                _chunk_input(
                    chunk_index=0,
                    text="Unrelated onboarding content.",
                    end_char=29,
                ),
            ],
        )

        context = self.service.build_context(
            self.db_path,
            company_id="company-a",
            query="vacation schedule",
        )

        self.assertEqual(context.source_count, 0)
        self.assertEqual(context.context_text, "")
        self.assertFalse(context.truncated)

    def test_company_tenant_isolation(self) -> None:
        doc_a = self._create_document(
            company_id="company-a",
            title="A",
            filename="a.pdf",
        )
        doc_b = self._create_document(
            company_id="company-b",
            title="B",
            filename="b.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=doc_a,
            chunks=[
                _chunk_input(
                    chunk_index=0,
                    text="Company A return policy.",
                    end_char=24,
                ),
            ],
        )
        self._replace_chunks(
            company_id="company-b",
            document_id=doc_b,
            chunks=[
                _chunk_input(
                    chunk_index=0,
                    text="Company B return policy.",
                    end_char=24,
                ),
            ],
        )

        context = self.service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(context.source_count, 1)
        self.assertEqual(context.sources[0].company_id, "company-a")
        self.assertIn("Company A", context.context_text)
        self.assertNotIn("Company B", context.context_text)

    def test_russian_unicode_query_and_content(self) -> None:
        document_id = self._create_document(
            company_id="company-a",
            title="Политика",
            filename="policy.pdf",
        )
        self._replace_chunks(
            company_id="company-a",
            document_id=document_id,
            chunks=[
                _chunk_input(
                    chunk_index=0,
                    text="Политика возврата товара для сотрудников.",
                    end_char=42,
                ),
            ],
        )

        context = self.service.build_context(
            self.db_path,
            company_id="company-a",
            query="политика возврата",
        )

        self.assertEqual(context.source_count, 1)
        self.assertIn("Политика возврата", context.context_text)


class KnowledgeRetrievalContextServiceDependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_custom_retrieval_limit_is_passed_to_retrieval_service(self) -> None:
        retrieval = _RecordingRetrievalService(results=())
        builder = _RecordingContextBuilder()
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
            retrieval_limit=7,
        )

        self.assertEqual(len(retrieval.calls), 1)
        self.assertEqual(retrieval.calls[0]["limit"], 7)

    def test_default_retrieval_limit_follows_context_max_sources(self) -> None:
        retrieval = _RecordingRetrievalService(results=())
        builder = _RecordingContextBuilder()
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(retrieval.calls[0]["limit"], DEFAULT_MAX_SOURCES)

    def test_explicit_options_max_sources_affects_retrieval_limit(self) -> None:
        retrieval = _RecordingRetrievalService(results=())
        builder = _RecordingContextBuilder()
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
            options=KnowledgeContextBuildingOptions(max_sources=3),
        )

        self.assertEqual(retrieval.calls[0]["limit"], 3)
        self.assertEqual(builder.calls[0]["options"].max_sources, 3)

    def test_explicit_retrieval_limit_can_exceed_max_sources(self) -> None:
        retrieval = _RecordingRetrievalService(results=())
        builder = _RecordingContextBuilder()
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
            retrieval_limit=10,
            options=KnowledgeContextBuildingOptions(max_sources=2),
        )

        self.assertEqual(retrieval.calls[0]["limit"], 10)
        self.assertEqual(builder.calls[0]["options"].max_sources, 2)

    def test_custom_context_builder_dependency_is_used(self) -> None:
        retrieval = _RecordingRetrievalService(results=())
        builder = _RecordingContextBuilder(
            context=KnowledgeRetrievalContext(
                query="return policy",
                sources=(),
                context_text="custom",
                source_count=0,
                total_chars=0,
                truncated=False,
            ),
        )
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        context = service.build_context(
            self.db_path,
            company_id="company-a",
            query="return policy",
        )

        self.assertEqual(context.context_text, "custom")
        self.assertEqual(len(builder.calls), 1)

    def test_custom_retrieval_service_dependency_is_used(self) -> None:
        from app.knowledge.models import KnowledgeDocumentChunk

        chunk = KnowledgeDocumentChunk(
            id=1,
            company_id="company-a",
            document_id="doc-1",
            chunk_index=0,
            text="Stub chunk text.",
            start_char=0,
            end_char=16,
            created_at="2026-01-01 00:00:00",
        )
        retrieval = _RecordingRetrievalService(
            results=[KnowledgeRetrievalResult(chunk=chunk, score=1.0)],
        )
        builder = _RecordingContextBuilder()
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        service.build_context(
            self.db_path,
            company_id="company-a",
            query="stub",
        )

        self.assertEqual(len(retrieval.calls), 1)
        self.assertEqual(len(builder.calls[0]["results"]), 1)

    def test_retrieval_service_errors_propagate(self) -> None:
        retrieval = _RecordingRetrievalService(
            error=KnowledgeRetrievalError("query must not be empty"),
        )
        builder = _RecordingContextBuilder()
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        with self.assertRaises(KnowledgeRetrievalError):
            service.build_context(
                self.db_path,
                company_id="company-a",
                query="   ",
            )

        self.assertEqual(len(builder.calls), 0)

    def test_context_builder_errors_propagate(self) -> None:
        retrieval = _RecordingRetrievalService(results=())
        builder = _RecordingContextBuilder(
            error=KnowledgeContextBuildingError("max_sources must be positive"),
        )
        service = KnowledgeRetrievalContextService(
            retrieval_service=retrieval,
            context_builder=builder,
        )

        with self.assertRaises(KnowledgeContextBuildingError):
            service.build_context(
                self.db_path,
                company_id="company-a",
                query="return policy",
                options=KnowledgeContextBuildingOptions(max_sources=0),
            )

        self.assertEqual(len(retrieval.calls), 1)
