"""Tests for Knowledge Base answer response parser."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_response_parser import (
    KnowledgeAnswerResponseParsingError,
    KnowledgeAnswerResponseParser,
)


def _valid_citation(
    source_number: int = 1,
    document_id: str = "doc-1",
    chunk_index: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "source_number": source_number,
        "document_id": document_id,
        "chunk_index": chunk_index,
    }
    if extra:
        payload.update(extra)
    return payload


def _valid_payload(
    answer: str = "Возврат оформляется в течение 14 дней.",
    sufficient_context: bool = True,
    citations: Optional[List[Dict[str, Any]]] = None,
    extra_root: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if citations is None:
        citations = [_valid_citation()]
    payload: Dict[str, Any] = {
        "answer": answer,
        "sufficient_context": sufficient_context,
        "citations": citations,
    }
    if extra_root:
        payload.update(extra_root)
    return payload


class KnowledgeAnswerResponseParserSuccessTests(unittest.TestCase):
    """Tests for successful knowledge-answer parsing."""

    def setUp(self) -> None:
        self.parser = KnowledgeAnswerResponseParser()

    def test_parse_full_valid_json(self) -> None:
        response = json.dumps(_valid_payload())

        result = self.parser.parse(response)

        self.assertIsInstance(result, KnowledgeAnswerResult)
        self.assertEqual(result.answer, "Возврат оформляется в течение 14 дней.")
        self.assertTrue(result.sufficient_context)
        self.assertEqual(len(result.citations), 1)
        self.assertIsInstance(result.citations[0], KnowledgeAnswerCitation)
        self.assertEqual(result.citations[0].source_number, 1)
        self.assertEqual(result.citations[0].document_id, "doc-1")
        self.assertEqual(result.citations[0].chunk_index, 0)

    def test_answer_trimmed(self) -> None:
        payload = _valid_payload(answer="  Trimmed answer.  ")
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.answer, "Trimmed answer.")

    def test_document_id_trimmed(self) -> None:
        payload = _valid_payload(
            citations=[_valid_citation(document_id="  doc-abc  ")]
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.citations[0].document_id, "doc-abc")

    def test_multiple_citations_preserve_order(self) -> None:
        payload = _valid_payload(
            citations=[
                _valid_citation(1, "doc-1", 0),
                _valid_citation(2, "doc-2", 3),
            ]
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(len(result.citations), 2)
        self.assertEqual(result.citations[0].source_number, 1)
        self.assertEqual(result.citations[1].source_number, 2)
        self.assertEqual(result.citations[1].document_id, "doc-2")
        self.assertEqual(result.citations[1].chunk_index, 3)

    def test_empty_citations_allowed(self) -> None:
        payload = _valid_payload(
            answer="Недостаточно информации.",
            sufficient_context=False,
            citations=[],
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.citations, ())
        self.assertFalse(result.sufficient_context)

    def test_sufficient_context_true_with_empty_citations_allowed(self) -> None:
        payload = _valid_payload(
            answer="Answer without citations.",
            sufficient_context=True,
            citations=[],
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertTrue(result.sufficient_context)
        self.assertEqual(result.citations, ())

    def test_sufficient_context_false_with_citations_allowed(self) -> None:
        payload = _valid_payload(
            answer="Partial context only.",
            sufficient_context=False,
            citations=[_valid_citation()],
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertFalse(result.sufficient_context)
        self.assertEqual(len(result.citations), 1)

    def test_duplicate_citations_preserved(self) -> None:
        duplicate = _valid_citation(1, "doc-1", 0)
        payload = _valid_payload(citations=[duplicate, duplicate])
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(len(result.citations), 2)
        self.assertEqual(result.citations[0], result.citations[1])

    def test_extra_root_fields_ignored(self) -> None:
        payload = _valid_payload(extra_root={"provider_metadata": "ignored"})
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.answer, "Возврат оформляется в течение 14 дней.")

    def test_extra_citation_fields_ignored(self) -> None:
        payload = _valid_payload(
            citations=[_valid_citation(extra={"confidence": 0.95})]
        )
        response = json.dumps(payload)

        result = self.parser.parse(response)

        self.assertEqual(result.citations[0].document_id, "doc-1")

    def test_unicode_answer_preserved(self) -> None:
        answer = "Қазақша жауап мәтіні."
        payload = _valid_payload(answer=answer)
        response = json.dumps(payload, ensure_ascii=False)

        result = self.parser.parse(response)

        self.assertEqual(result.answer, answer)

    def test_identical_json_produces_equal_results(self) -> None:
        response = json.dumps(_valid_payload())

        first = self.parser.parse(response)
        second = self.parser.parse(response)

        self.assertEqual(first, second)


class KnowledgeAnswerResponseParserErrorTests(unittest.TestCase):
    """Tests for knowledge-answer parsing errors."""

    def setUp(self) -> None:
        self.parser = KnowledgeAnswerResponseParser()

    def test_empty_response_rejected(self) -> None:
        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse("")

        self.assertEqual(str(context.exception), "Response must not be empty.")

    def test_whitespace_only_response_rejected(self) -> None:
        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse("   \n\t  ")

        self.assertEqual(str(context.exception), "Response must not be empty.")

    def test_malformed_json_rejected(self) -> None:
        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse("{not valid json")

        self.assertEqual(str(context.exception), "Response must be valid JSON.")

    def test_markdown_fenced_json_rejected(self) -> None:
        fenced = "```json\n" + json.dumps(_valid_payload()) + "\n```"

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(fenced)

        self.assertEqual(str(context.exception), "Response must be valid JSON.")

    def test_json_string_root_rejected(self) -> None:
        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps("hello"))

        self.assertEqual(
            str(context.exception),
            "Response root must be a JSON object.",
        )

    def test_json_null_root_rejected(self) -> None:
        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse("null")

        self.assertEqual(
            str(context.exception),
            "Response root must be a JSON object.",
        )

    def test_non_object_root_rejected(self) -> None:
        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps([]))

        self.assertEqual(
            str(context.exception),
            "Response root must be a JSON object.",
        )

    def test_missing_answer(self) -> None:
        payload = _valid_payload()
        del payload["answer"]

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'answer' is required.")

    def test_missing_sufficient_context(self) -> None:
        payload = _valid_payload()
        del payload["sufficient_context"]

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'sufficient_context' is required.",
        )

    def test_missing_citations(self) -> None:
        payload = _valid_payload()
        del payload["citations"]

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(str(context.exception), "Field 'citations' is required.")

    def test_answer_invalid_types(self) -> None:
        for value in (123, True, None, [], {}):
            with self.subTest(value=value):
                payload = _valid_payload(answer=value)  # type: ignore[arg-type]

                with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'answer' must be a string.",
                )

    def test_answer_empty_after_trim_rejected(self) -> None:
        for value in ("", "   ", "\n\t"):
            with self.subTest(value=value):
                payload = _valid_payload(answer=value)

                with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'answer' must not be empty.",
                )

    def test_sufficient_context_invalid_types(self) -> None:
        for value in ("true", 1, 0, None, []):
            with self.subTest(value=value):
                payload = _valid_payload(sufficient_context=value)  # type: ignore[arg-type]

                with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Field 'sufficient_context' must be a boolean.",
                )

    def test_citations_not_list(self) -> None:
        payload = _valid_payload(citations="not a list")  # type: ignore[arg-type]

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Field 'citations' must be a list.",
        )

    def test_citation_not_object(self) -> None:
        payload = _valid_payload(citations=["not an object"])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 must be a JSON object.",
        )

    def test_citation_missing_source_number(self) -> None:
        citation = _valid_citation()
        del citation["source_number"]
        payload = _valid_payload(citations=[citation])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 is missing 'source_number'.",
        )

    def test_citation_missing_document_id(self) -> None:
        citation = _valid_citation()
        del citation["document_id"]
        payload = _valid_payload(citations=[citation])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 is missing 'document_id'.",
        )

    def test_citation_missing_chunk_index(self) -> None:
        citation = _valid_citation()
        del citation["chunk_index"]
        payload = _valid_payload(citations=[citation])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 is missing 'chunk_index'.",
        )

    def test_citation_source_number_invalid_types(self) -> None:
        for value in ("1", 1.0, True, None):
            with self.subTest(value=value):
                payload = _valid_payload(
                    citations=[_valid_citation(source_number=value)]  # type: ignore[arg-type]
                )

                with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Citation at index 0 field 'source_number' must be an integer.",
                )

    def test_citation_source_number_zero_rejected(self) -> None:
        payload = _valid_payload(citations=[_valid_citation(source_number=0)])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 field 'source_number' must be >= 1.",
        )

    def test_citation_source_number_negative_rejected(self) -> None:
        payload = _valid_payload(citations=[_valid_citation(source_number=-1)])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 field 'source_number' must be >= 1.",
        )

    def test_citation_document_id_invalid_type(self) -> None:
        payload = _valid_payload(
            citations=[_valid_citation(document_id=123)]  # type: ignore[arg-type]
        )

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 field 'document_id' must be a string.",
        )

    def test_citation_document_id_empty_after_trim_rejected(self) -> None:
        payload = _valid_payload(citations=[_valid_citation(document_id="   ")])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 field 'document_id' must not be empty.",
        )

    def test_citation_chunk_index_invalid_types(self) -> None:
        for value in ("0", 0.0, True, None):
            with self.subTest(value=value):
                payload = _valid_payload(
                    citations=[_valid_citation(chunk_index=value)]  # type: ignore[arg-type]
                )

                with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
                    self.parser.parse(json.dumps(payload))

                self.assertEqual(
                    str(context.exception),
                    "Citation at index 0 field 'chunk_index' must be an integer.",
                )

    def test_citation_chunk_index_negative_rejected(self) -> None:
        payload = _valid_payload(citations=[_valid_citation(chunk_index=-1)])

        with self.assertRaises(KnowledgeAnswerResponseParsingError) as context:
            self.parser.parse(json.dumps(payload))

        self.assertEqual(
            str(context.exception),
            "Citation at index 0 field 'chunk_index' must be >= 0.",
        )

    def test_parsing_error_exposes_message_attribute(self) -> None:
        error = KnowledgeAnswerResponseParsingError("test message")

        self.assertEqual(error.message, "test message")
        self.assertEqual(str(error), "test message")
