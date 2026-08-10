"""Tests for Knowledge Base retrieval context building."""

from __future__ import annotations

import unittest
from typing import Optional, Sequence

from app.knowledge.context_builder import (
    DEFAULT_MAX_SOURCES,
    DEFAULT_MAX_TOTAL_CHARS,
    KnowledgeContextBuildingError,
    KnowledgeContextBuildingOptions,
    KnowledgeContextSource,
    KnowledgeRetrievalContext,
    KnowledgeRetrievalContextBuilder,
)
from app.knowledge.models import KnowledgeDocumentChunk
from app.knowledge.retrieval import KnowledgeRetrievalResult


def _chunk(
    *,
    chunk_id: int = 1,
    company_id: str = "company-a",
    document_id: str = "doc-1",
    chunk_index: int = 0,
    text: str = "Sample chunk text.",
    start_char: int = 0,
    end_char: int = 18,
) -> KnowledgeDocumentChunk:
    return KnowledgeDocumentChunk(
        id=chunk_id,
        company_id=company_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        start_char=start_char,
        end_char=end_char,
        created_at="2026-01-01 00:00:00",
    )


def _result(
    chunk: KnowledgeDocumentChunk,
    score: float = 1.0,
) -> KnowledgeRetrievalResult:
    return KnowledgeRetrievalResult(chunk=chunk, score=score)


class KnowledgeRetrievalContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = KnowledgeRetrievalContextBuilder()

    def _build(
        self,
        *,
        company_id: str = "company-a",
        query: str = "return policy",
        results: Sequence[KnowledgeRetrievalResult],
        options: Optional[KnowledgeContextBuildingOptions] = None,
    ) -> KnowledgeRetrievalContext:
        return self.builder.build(
            company_id=company_id,
            query=query,
            results=results,
            options=options,
        )

    def test_one_result(self) -> None:
        chunk = _chunk(text="Return policy details for employees.")
        context = self._build(results=[_result(chunk)])

        self.assertEqual(context.source_count, 1)
        self.assertEqual(len(context.sources), 1)
        self.assertIn("Return policy details", context.context_text)
        self.assertIn("document=doc-1", context.context_text)
        self.assertIn("chunk=0", context.context_text)
        self.assertFalse(context.truncated)

    def test_multiple_results(self) -> None:
        results = [
            _result(_chunk(chunk_index=0, text="First relevant chunk.")),
            _result(_chunk(chunk_index=1, text="Second relevant chunk.", chunk_id=2)),
        ]
        context = self._build(results=results)

        self.assertEqual(context.source_count, 2)
        self.assertIn("First relevant chunk.", context.context_text)
        self.assertIn("Second relevant chunk.", context.context_text)
        self.assertIn("[Source 1 |", context.context_text)
        self.assertIn("[Source 2 |", context.context_text)

    def test_ranking_order_preserved(self) -> None:
        results = [
            _result(_chunk(document_id="doc-a", chunk_index=0, text="Alpha chunk."), 0.9),
            _result(_chunk(document_id="doc-b", chunk_index=1, text="Beta chunk.", chunk_id=2), 0.8),
            _result(_chunk(document_id="doc-c", chunk_index=2, text="Gamma chunk.", chunk_id=3), 0.7),
        ]
        context = self._build(results=results)

        self.assertEqual(context.sources[0].document_id, "doc-a")
        self.assertEqual(context.sources[1].document_id, "doc-b")
        self.assertEqual(context.sources[2].document_id, "doc-c")
        self.assertLess(
            context.context_text.index("Alpha chunk."),
            context.context_text.index("Beta chunk."),
        )
        self.assertLess(
            context.context_text.index("Beta chunk."),
            context.context_text.index("Gamma chunk."),
        )

    def test_empty_result_set(self) -> None:
        context = self._build(results=[])

        self.assertEqual(context.sources, ())
        self.assertEqual(context.context_text, "")
        self.assertEqual(context.source_count, 0)
        self.assertEqual(context.total_chars, 0)
        self.assertFalse(context.truncated)

    def test_max_sources_respected(self) -> None:
        results = [
            _result(_chunk(chunk_index=index, text=f"Chunk {index}.", chunk_id=index + 1))
            for index in range(10)
        ]
        context = self._build(
            results=results,
            options=KnowledgeContextBuildingOptions(max_sources=3, max_total_chars=10000),
        )

        self.assertEqual(context.source_count, 3)
        self.assertEqual(len(context.sources), 3)

    def test_max_total_chars_respected(self) -> None:
        long_text = "A" * 500
        results = [
            _result(_chunk(chunk_index=0, text=long_text)),
            _result(_chunk(chunk_index=1, text=long_text, chunk_id=2)),
        ]
        context = self._build(
            results=results,
            options=KnowledgeContextBuildingOptions(
                max_sources=5,
                max_total_chars=600,
            ),
        )

        self.assertLessEqual(len(context.context_text), 600)
        self.assertTrue(context.truncated)

    def test_final_source_truncation(self) -> None:
        chunk = _chunk(text="Return policy " + ("details " * 50))
        context = self._build(
            results=[_result(chunk)],
            options=KnowledgeContextBuildingOptions(
                max_sources=1,
                max_total_chars=80,
            ),
        )

        self.assertTrue(context.truncated)
        self.assertEqual(context.source_count, 1)
        self.assertLess(len(context.sources[0].text), len(chunk.text))
        self.assertLessEqual(len(context.context_text), 80)
        self.assertTrue(context.sources[0].text.strip())

    def test_truncated_flag_set(self) -> None:
        context = self._build(
            results=[_result(_chunk(text="X" * 200))],
            options=KnowledgeContextBuildingOptions(max_total_chars=50),
        )
        self.assertTrue(context.truncated)

    def test_exact_boundary_behavior(self) -> None:
        chunk = _chunk(text="Exact fit text.")
        header = "[Source 1 | document=doc-1 | chunk=0]\n"
        max_chars = len(header) + len(chunk.text)

        context = self._build(
            results=[_result(chunk)],
            options=KnowledgeContextBuildingOptions(max_total_chars=max_chars),
        )

        self.assertEqual(len(context.context_text), max_chars)
        self.assertEqual(context.sources[0].text, chunk.text)
        self.assertFalse(context.truncated)

    def test_russian_text(self) -> None:
        text = "Политика возврата товара для сотрудников магазина."
        context = self._build(
            query="политика возврата",
            results=[_result(_chunk(text=text))],
        )

        self.assertIn("Политика возврата", context.context_text)
        self.assertEqual(context.sources[0].text, text)

    def test_kazakh_unicode_text(self) -> None:
        text = "Қайтару саясаты мен қызметкерлерге арналған нұсқаулық."
        context = self._build(
            query="қайтару",
            results=[_result(_chunk(text=text))],
        )

        self.assertIn("Қайтару", context.context_text)
        self.assertEqual(context.sources[0].text, text)

    def test_english_text(self) -> None:
        text = "Employee return policy and refund procedure."
        context = self._build(
            query="return policy",
            results=[_result(_chunk(text=text))],
        )

        self.assertIn("Employee return policy", context.context_text)

    def test_empty_company_rejected(self) -> None:
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(company_id="  ", results=[])

    def test_empty_query_rejected(self) -> None:
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(query="  ", results=[])

    def test_zero_max_sources_rejected(self) -> None:
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(
                results=[_result(_chunk())],
                options=KnowledgeContextBuildingOptions(max_sources=0),
            )

    def test_negative_max_sources_rejected(self) -> None:
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(
                results=[_result(_chunk())],
                options=KnowledgeContextBuildingOptions(max_sources=-1),
            )

    def test_zero_max_total_chars_rejected(self) -> None:
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(
                results=[_result(_chunk())],
                options=KnowledgeContextBuildingOptions(max_total_chars=0),
            )

    def test_negative_max_total_chars_rejected(self) -> None:
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(
                results=[_result(_chunk())],
                options=KnowledgeContextBuildingOptions(max_total_chars=-10),
            )

    def test_tenant_mismatch_raises(self) -> None:
        chunk = _chunk(company_id="company-b")
        with self.assertRaises(KnowledgeContextBuildingError) as error:
            self._build(company_id="company-a", results=[_result(chunk)])

        self.assertIn("company", error.exception.message.lower())

    def test_same_document_id_different_tenants_cannot_leak(self) -> None:
        chunk = _chunk(company_id="company-b", document_id="shared-doc")
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(company_id="company-a", results=[_result(chunk)])

    def test_source_metadata_preserved(self) -> None:
        chunk = _chunk(
            document_id="policy-doc",
            chunk_index=3,
            text="Metadata test chunk.",
            start_char=100,
            end_char=120,
        )
        context = self._build(results=[_result(chunk)])
        source = context.sources[0]

        self.assertEqual(source.company_id, "company-a")
        self.assertEqual(source.document_id, "policy-doc")
        self.assertEqual(source.chunk_index, 3)
        self.assertEqual(source.start_char, 100)
        self.assertEqual(source.end_char, 120)

    def test_deterministic_repeated_calls(self) -> None:
        results = [
            _result(_chunk(chunk_index=0, text="First.")),
            _result(_chunk(chunk_index=1, text="Second.", chunk_id=2)),
        ]
        first = self._build(results=results)
        second = self._build(results=results)

        self.assertEqual(first, second)

    def test_input_results_not_mutated(self) -> None:
        chunk = _chunk(text="Immutable chunk.")
        result = _result(chunk)
        original_score = result.score
        original_text = result.chunk.text

        self._build(results=[result])

        self.assertEqual(result.score, original_score)
        self.assertEqual(result.chunk.text, original_text)

    def test_no_filesystem_path_in_context(self) -> None:
        context = self._build(
            results=[_result(_chunk(text="Safe content without paths."))],
        )

        self.assertNotIn("/Users/", context.context_text)
        self.assertNotIn("\\", context.context_text)
        self.assertNotIn(".db", context.context_text)

    def test_source_count_and_total_chars_correct(self) -> None:
        text_one = "First chunk body."
        text_two = "Second chunk body."
        results = [
            _result(_chunk(chunk_index=0, text=text_one)),
            _result(_chunk(chunk_index=1, text=text_two, chunk_id=2)),
        ]
        context = self._build(results=results)

        self.assertEqual(context.source_count, 2)
        self.assertEqual(context.total_chars, len(text_one) + len(text_two))

    def test_does_not_add_empty_source_when_space_too_small(self) -> None:
        header = "[Source 1 | document=doc-1 | chunk=0]\n"
        context = self._build(
            results=[_result(_chunk(text="Too long to fit meaningfully."))],
            options=KnowledgeContextBuildingOptions(max_total_chars=len(header)),
        )

        self.assertEqual(context.source_count, 0)
        self.assertEqual(context.context_text, "")
        self.assertFalse(context.truncated)

    def test_whitespace_only_truncated_text_not_added(self) -> None:
        header = "[Source 1 | document=doc-1 | chunk=0]\n"
        # Budget fits header plus one space from chunk text "   meaningful"
        context = self._build(
            results=[_result(_chunk(text="   meaningful content"))],
            options=KnowledgeContextBuildingOptions(max_total_chars=len(header) + 1),
        )

        self.assertEqual(context.source_count, 0)
        self.assertEqual(context.context_text, "")

    def test_unicode_truncation_preserves_characters(self) -> None:
        text = "Қайтару " * 30
        context = self._build(
            results=[_result(_chunk(text=text))],
            options=KnowledgeContextBuildingOptions(max_total_chars=60),
        )

        self.assertTrue(context.truncated)
        self.assertLess(len(context.sources[0].text), len(text))
        for char in context.sources[0].text:
            self.assertLess(ord(char), 0x110000)

    def test_default_options(self) -> None:
        options = KnowledgeContextBuildingOptions()
        self.assertEqual(options.max_sources, DEFAULT_MAX_SOURCES)
        self.assertEqual(options.max_total_chars, DEFAULT_MAX_TOTAL_CHARS)

    def test_custom_separator(self) -> None:
        results = [
            _result(_chunk(chunk_index=0, text="One.")),
            _result(_chunk(chunk_index=1, text="Two.", chunk_id=2)),
        ]
        context = self._build(
            results=results,
            options=KnowledgeContextBuildingOptions(separator="\n---\n"),
        )

        self.assertIn("\n---\n", context.context_text)

    def test_query_stored_normalized(self) -> None:
        context = self._build(query="  return policy  ", results=[])
        self.assertEqual(context.query, "return policy")

    def test_stops_after_truncated_source(self) -> None:
        results = [
            _result(_chunk(chunk_index=0, text="A" * 100)),
            _result(_chunk(chunk_index=1, text="Should not appear.", chunk_id=2)),
        ]
        context = self._build(
            results=results,
            options=KnowledgeContextBuildingOptions(max_total_chars=80),
        )

        self.assertEqual(context.source_count, 1)
        self.assertNotIn("Should not appear.", context.context_text)

    def test_context_source_is_immutable_dataclass(self) -> None:
        source = KnowledgeContextSource(
            company_id="company-a",
            document_id="doc-1",
            chunk_index=0,
            text="Sample.",
            start_char=0,
            end_char=6,
        )
        with self.assertRaises(AttributeError):
            source.text = "Changed"  # type: ignore[misc]

    def test_mismatch_on_second_result_raises(self) -> None:
        results = [
            _result(_chunk(company_id="company-a", chunk_index=0, text="Valid.")),
            _result(
                _chunk(
                    company_id="company-b",
                    chunk_index=1,
                    text="Invalid tenant.",
                    chunk_id=2,
                )
            ),
        ]
        with self.assertRaises(KnowledgeContextBuildingError):
            self._build(company_id="company-a", results=results)


class KnowledgeContextBuilderHelperTests(unittest.TestCase):
    def test_knowledge_retrieval_context_fields(self) -> None:
        context = KnowledgeRetrievalContext(
            query="test",
            sources=(),
            context_text="",
            source_count=0,
            total_chars=0,
            truncated=False,
        )
        self.assertEqual(context.query, "test")
        self.assertFalse(context.truncated)


if __name__ == "__main__":
    unittest.main()
