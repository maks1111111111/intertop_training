"""Tests for Knowledge Base answer data contracts."""

from __future__ import annotations

import unittest
from typing import Tuple

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerAI,
    KnowledgeAnswerCitation,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.knowledge.context_builder import KnowledgeRetrievalContext


def _sample_context(
    query: str = "Как оформить возврат?",
    context_text: str = "[Source 1 | document=doc-1 | chunk=0]\nReturn policy text.",
    source_count: int = 1,
) -> KnowledgeRetrievalContext:
    return KnowledgeRetrievalContext(
        query=query,
        sources=(),
        context_text=context_text,
        source_count=source_count,
        total_chars=len(context_text),
        truncated=False,
    )


class KnowledgeAnswerCitationTests(unittest.TestCase):
    """Tests for :class:`KnowledgeAnswerCitation`."""

    def test_create_citation(self) -> None:
        citation = KnowledgeAnswerCitation(
            source_number=1,
            document_id="doc-abc",
            chunk_index=0,
        )

        self.assertEqual(citation.source_number, 1)
        self.assertEqual(citation.document_id, "doc-abc")
        self.assertEqual(citation.chunk_index, 0)

    def test_immutable(self) -> None:
        citation = KnowledgeAnswerCitation(
            source_number=1,
            document_id="doc-abc",
            chunk_index=0,
        )

        with self.assertRaises(AttributeError):
            citation.source_number = 2  # type: ignore[misc]

    def test_equality(self) -> None:
        left = KnowledgeAnswerCitation(1, "doc-abc", 0)
        right = KnowledgeAnswerCitation(1, "doc-abc", 0)

        self.assertEqual(left, right)


class KnowledgeAnswerRequestTests(unittest.TestCase):
    """Tests for :class:`KnowledgeAnswerRequest`."""

    def test_create_request(self) -> None:
        context = _sample_context()
        request = KnowledgeAnswerRequest(
            question="Как оформить возврат?",
            context=context,
            language="ru",
        )

        self.assertEqual(request.question, "Как оформить возврат?")
        self.assertIs(request.context, context)
        self.assertEqual(request.language, "ru")

    def test_default_language(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_sample_context(),
        )

        self.assertEqual(request.language, "ru")


class KnowledgeAnswerResultTests(unittest.TestCase):
    """Tests for :class:`KnowledgeAnswerResult`."""

    def test_create_result(self) -> None:
        citations: Tuple[KnowledgeAnswerCitation, ...] = (
            KnowledgeAnswerCitation(1, "doc-1", 0),
        )
        result = KnowledgeAnswerResult(
            answer="Возврат оформляется в течение 14 дней.",
            citations=citations,
            sufficient_context=True,
        )

        self.assertEqual(result.answer, "Возврат оформляется в течение 14 дней.")
        self.assertEqual(result.citations, citations)
        self.assertTrue(result.sufficient_context)

    def test_empty_citations_allowed(self) -> None:
        result = KnowledgeAnswerResult(
            answer="Недостаточно информации.",
            citations=(),
            sufficient_context=False,
        )

        self.assertEqual(result.citations, ())
        self.assertIsInstance(result.citations, tuple)
        self.assertFalse(result.sufficient_context)


class KnowledgeAnswerAIProtocolTests(unittest.TestCase):
    """Tests for :class:`KnowledgeAnswerAI` protocol compatibility."""

    def test_fake_provider_satisfies_protocol(self) -> None:
        expected_result = KnowledgeAnswerResult(
            answer="Answer text.",
            citations=(KnowledgeAnswerCitation(1, "doc-1", 0),),
            sufficient_context=True,
        )

        class FakeAnswerAI:
            def answer(self, request: KnowledgeAnswerRequest) -> KnowledgeAnswerResult:
                self.last_request = request
                return expected_result

        provider: KnowledgeAnswerAI = FakeAnswerAI()
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_sample_context(),
        )

        result = provider.answer(request)

        self.assertIs(result, expected_result)
        self.assertIs(provider.last_request, request)  # type: ignore[attr-defined]
