"""Tests for Knowledge Base answer semantic validator."""

from __future__ import annotations

import unittest
from typing import Optional

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_validator import (
    KnowledgeAnswerValidationError,
    KnowledgeAnswerValidator,
)
from app.knowledge.context_builder import (
    KnowledgeContextSource,
    KnowledgeRetrievalContext,
)


def _source(
    document_id: str = "doc-1",
    chunk_index: int = 0,
    text: str = "Return policy text.",
    company_id: str = "company-a",
) -> KnowledgeContextSource:
    return KnowledgeContextSource(
        company_id=company_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        start_char=0,
        end_char=len(text),
    )


def _context(
    sources: tuple[KnowledgeContextSource, ...] = (),
    query: str = "Как оформить возврат?",
    context_text: str = "",
    source_count: Optional[int] = None,
) -> KnowledgeRetrievalContext:
    if source_count is None:
        source_count = len(sources)
    if not context_text and sources:
        parts = []
        for index, source in enumerate(sources, start=1):
            parts.append(
                f"[Source {index} | document={source.document_id} | "
                f"chunk={source.chunk_index}]\n{source.text}"
            )
        context_text = "\n\n".join(parts)
    return KnowledgeRetrievalContext(
        query=query,
        sources=sources,
        context_text=context_text,
        source_count=source_count,
        total_chars=len(context_text),
        truncated=False,
    )


def _result(
    answer: str = "Возврат оформляется в течение 14 дней.",
    citations: tuple[KnowledgeAnswerCitation, ...] = (
        KnowledgeAnswerCitation(1, "doc-1", 0),
    ),
    sufficient_context: bool = True,
) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer,
        citations=citations,
        sufficient_context=sufficient_context,
    )


class KnowledgeAnswerValidatorSuccessTests(unittest.TestCase):
    """Tests for successful validation."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()

    def test_sufficient_context_true_one_valid_citation(self) -> None:
        context = _context(sources=(_source(),))
        result = _result()

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations, result.citations)
        self.assertEqual(validated.citations[0].source_number, 1)

    def test_sufficient_context_true_multiple_valid_citations(self) -> None:
        sources = (
            _source(document_id="doc-1", chunk_index=0, text="First."),
            _source(document_id="doc-2", chunk_index=1, text="Second."),
        )
        context = _context(sources=sources)
        result = _result(
            citations=(
                KnowledgeAnswerCitation(1, "doc-1", 0),
                KnowledgeAnswerCitation(2, "doc-2", 1),
            )
        )

        validated = self.validator.validate(result, context)

        self.assertEqual(len(validated.citations), 2)

    def test_sufficient_context_false_empty_citations(self) -> None:
        context = _context(sources=(_source(),))
        result = _result(citations=(), sufficient_context=False)

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations, ())

    def test_sufficient_context_false_valid_citation(self) -> None:
        context = _context(sources=(_source(),))
        result = _result(
            answer="Доступной информации недостаточно для полного ответа.",
            citations=(KnowledgeAnswerCitation(1, "doc-1", 0),),
            sufficient_context=False,
        )

        validated = self.validator.validate(result, context)

        self.assertIs(validated, result)

    def test_citation_to_second_source_resolves_correctly(self) -> None:
        sources = (
            _source(document_id="policy-a", chunk_index=0, text="First."),
            _source(document_id="policy-b", chunk_index=3, text="Second."),
        )
        context = _context(sources=sources)
        result = _result(
            citations=(KnowledgeAnswerCitation(2, "policy-b", 3),)
        )

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations[0].source_number, 2)
        self.assertEqual(validated.citations[0].document_id, "policy-b")
        self.assertEqual(validated.citations[0].chunk_index, 3)

    def test_unicode_answer_preserved(self) -> None:
        answer = "Возврат: Қазақша мәтін және English text."
        context = _context(sources=(_source(),))
        result = _result(answer=answer)

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.answer, answer)


class KnowledgeAnswerValidatorSourceMatchFailureTests(unittest.TestCase):
    """Tests for citation source matching failures."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()
        self.context = _context(sources=(_source(document_id="policy-a", chunk_index=3),))

    def test_fabricated_document_id_rejected(self) -> None:
        result = _result(citations=(KnowledgeAnswerCitation(1, "policy-b", 3),))

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("does not match", ctx.exception.message)

    def test_correct_document_id_wrong_chunk_index_rejected(self) -> None:
        result = _result(citations=(KnowledgeAnswerCitation(1, "policy-a", 4),))

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("does not match", ctx.exception.message)

    def test_fabricated_document_chunk_pair_rejected(self) -> None:
        sources = (
            _source(document_id="policy-a", chunk_index=0),
            _source(document_id="policy-b", chunk_index=1),
        )
        context = _context(sources=sources)
        result = _result(citations=(KnowledgeAnswerCitation(1, "policy-c", 99),))

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, context)

        self.assertIn("does not match", ctx.exception.message)


class KnowledgeAnswerValidatorCanonicalizationTests(unittest.TestCase):
    """Tests for citation canonicalization from document/chunk identity."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()

    def test_wrong_in_range_source_number_accepted_and_canonicalized(self) -> None:
        sources = (
            _source(document_id="policy-a", chunk_index=0),
            _source(document_id="policy-b", chunk_index=1),
        )
        context = _context(sources=sources)
        result = _result(citations=(KnowledgeAnswerCitation(2, "policy-a", 0),))

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations[0].source_number, 1)
        self.assertEqual(validated.citations[0].document_id, "policy-a")
        self.assertEqual(validated.citations[0].chunk_index, 0)

    def test_out_of_range_source_number_accepted_and_canonicalized(self) -> None:
        context = _context(sources=(_source(document_id="policy-a", chunk_index=3),))
        result = _result(citations=(KnowledgeAnswerCitation(99, "policy-a", 3),))

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations[0].source_number, 1)

    def test_source_number_zero_with_valid_document_chunk_canonicalized(self) -> None:
        context = _context(sources=(_source(document_id="policy-a", chunk_index=3),))
        result = _result(citations=(KnowledgeAnswerCitation(0, "policy-a", 3),))

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations[0].source_number, 1)

    def test_source_number_six_with_five_sources_canonicalized_to_five(self) -> None:
        sources = (
            _source(document_id="512bd4f786724476a7ab2313e06a6554", chunk_index=11),
            _source(document_id="d4d35885d985418c93f45f3a05474720", chunk_index=11),
            _source(document_id="512bd4f786724476a7ab2313e06a6554", chunk_index=4),
            _source(document_id="512bd4f786724476a7ab2313e06a6554", chunk_index=5),
            _source(document_id="512bd4f786724476a7ab2313e06a6554", chunk_index=6),
        )
        context = _context(sources=sources)
        result = _result(
            citations=(
                KnowledgeAnswerCitation(3, "512bd4f786724476a7ab2313e06a6554", 4),
                KnowledgeAnswerCitation(4, "512bd4f786724476a7ab2313e06a6554", 5),
                KnowledgeAnswerCitation(6, "512bd4f786724476a7ab2313e06a6554", 6),
                KnowledgeAnswerCitation(
                    1, "d4d35885d985418c93f45f3a05474720", 11
                ),
            )
        )

        validated = self.validator.validate(result, context)

        self.assertEqual(len(validated.citations), 4)
        self.assertEqual(validated.citations[0].source_number, 3)
        self.assertEqual(validated.citations[0].chunk_index, 4)
        self.assertEqual(validated.citations[1].source_number, 4)
        self.assertEqual(validated.citations[1].chunk_index, 5)
        self.assertEqual(validated.citations[2].source_number, 5)
        self.assertEqual(validated.citations[2].chunk_index, 6)
        self.assertEqual(validated.citations[3].source_number, 2)
        self.assertEqual(validated.citations[3].document_id, "d4d35885d985418c93f45f3a05474720")

    def test_wrong_source_number_for_second_source_canonicalized(self) -> None:
        sources = (
            _source(document_id="policy-a", chunk_index=0),
            _source(document_id="policy-b", chunk_index=1),
        )
        context = _context(sources=sources)
        result = _result(citations=(KnowledgeAnswerCitation(1, "policy-b", 1),))

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations[0].source_number, 2)
        self.assertEqual(validated.citations[0].document_id, "policy-b")
        self.assertEqual(validated.citations[0].chunk_index, 1)

    def test_valid_citations_preserve_original_order(self) -> None:
        sources = (
            _source(document_id="doc-1", chunk_index=0),
            _source(document_id="doc-2", chunk_index=1),
            _source(document_id="doc-3", chunk_index=2),
        )
        context = _context(sources=sources)
        result = _result(
            citations=(
                KnowledgeAnswerCitation(9, "doc-3", 2),
                KnowledgeAnswerCitation(8, "doc-1", 0),
            )
        )

        validated = self.validator.validate(result, context)

        self.assertEqual(validated.citations[0].source_number, 3)
        self.assertEqual(validated.citations[0].document_id, "doc-3")
        self.assertEqual(validated.citations[1].source_number, 1)
        self.assertEqual(validated.citations[1].document_id, "doc-1")

    def test_already_canonical_citations_return_same_result(self) -> None:
        context = _context(sources=(_source(),))
        result = _result()

        validated = self.validator.validate(result, context)

        self.assertIs(validated, result)


class KnowledgeAnswerValidatorDuplicateTests(unittest.TestCase):
    """Tests for duplicate citation detection."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()
        self.context = _context(sources=(_source(),))

    def test_exact_duplicate_citation_rejected(self) -> None:
        duplicate = KnowledgeAnswerCitation(1, "doc-1", 0)
        result = _result(citations=(duplicate, duplicate))

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("duplicate citations", ctx.exception.message)

    def test_different_source_numbers_same_document_chunk_rejected(self) -> None:
        result = _result(
            citations=(
                KnowledgeAnswerCitation(1, "doc-1", 0),
                KnowledgeAnswerCitation(3, "doc-1", 0),
            )
        )

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("duplicate citations", ctx.exception.message)


class KnowledgeAnswerValidatorSufficientContextTests(unittest.TestCase):
    """Tests for sufficient_context consistency rules."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()

    def test_sufficient_context_true_empty_citations_rejected(self) -> None:
        context = _context(sources=(_source(),))
        result = _result(citations=(), sufficient_context=True)

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, context)

        self.assertIn("at least one valid citation", ctx.exception.message)

    def test_sufficient_context_true_empty_context_rejected(self) -> None:
        context = _context()
        result = _result(citations=(), sufficient_context=True)

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, context)

        self.assertIn("sufficient_context=true with empty context", ctx.exception.message)

    def test_sufficient_context_false_empty_context_empty_citations_accepted(
        self,
    ) -> None:
        context = _context()
        result = _result(
            answer="Недостаточно корпоративных источников для ответа.",
            citations=(),
            sufficient_context=False,
        )

        validated = self.validator.validate(result, context)

        self.assertIs(validated, result)

    def test_sufficient_context_false_empty_context_nonempty_citations_rejected(
        self,
    ) -> None:
        context = _context()
        result = _result(
            citations=(KnowledgeAnswerCitation(1, "doc-1", 0),),
            sufficient_context=False,
        )

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, context)

        self.assertIn("must be empty when context has no sources", ctx.exception.message)


class KnowledgeAnswerValidatorContextConsistencyTests(unittest.TestCase):
    """Tests for retrieval context internal consistency."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()
        self.result = _result(citations=(), sufficient_context=False)

    def test_source_count_lower_than_sources_rejected(self) -> None:
        context = _context(
            sources=(_source(), _source(document_id="doc-2", chunk_index=1)),
            source_count=1,
        )

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(self.result, context)

        self.assertIn("inconsistent", ctx.exception.message)

    def test_source_count_higher_than_sources_rejected(self) -> None:
        context = _context(sources=(_source(),), source_count=2)

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(self.result, context)

        self.assertIn("inconsistent", ctx.exception.message)

    def test_zero_sources_with_nonempty_context_text_rejected(self) -> None:
        context = _context(
            sources=(),
            context_text="[Source 1 | document=doc-1 | chunk=0]\nText.",
            source_count=0,
        )

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(self.result, context)

        self.assertIn("inconsistent", ctx.exception.message)


class KnowledgeAnswerValidatorDefensiveTests(unittest.TestCase):
    """Tests for defensive validation when called independently."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()
        self.context = _context(sources=(_source(),))

    def test_whitespace_answer_rejected(self) -> None:
        result = _result(answer="   ")

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("must not be empty", ctx.exception.message)


class KnowledgeAnswerValidatorSecurityTests(unittest.TestCase):
    """Tests for citation identity security."""

    def setUp(self) -> None:
        self.validator = KnowledgeAnswerValidator()
        self.context = _context(
            sources=(_source(document_id="policy-a", chunk_index=3),)
        )

    def test_mismatched_document_id_never_passes_with_matching_chunk(self) -> None:
        result = _result(citations=(KnowledgeAnswerCitation(1, "policy-b", 3),))

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("does not match", ctx.exception.message)

    def test_mismatched_chunk_index_never_passes_with_matching_document(self) -> None:
        result = _result(citations=(KnowledgeAnswerCitation(1, "policy-a", 99),))

        with self.assertRaises(KnowledgeAnswerValidationError) as ctx:
            self.validator.validate(result, self.context)

        self.assertIn("does not match", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
