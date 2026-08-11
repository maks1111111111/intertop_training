"""Tests for KnowledgeQuestionAnsweringService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_service import KnowledgeAnswerGenerationError
from app.knowledge.context_builder import (
    KnowledgeContextBuildingError,
    KnowledgeContextBuildingOptions,
    KnowledgeContextSource,
    KnowledgeRetrievalContext,
)
from app.knowledge.context_service import KnowledgeRetrievalContextService
from app.knowledge.question_answering_service import (
    KnowledgeQuestionAnsweringError,
    KnowledgeQuestionAnsweringService,
)
from app.knowledge.retrieval import KnowledgeRetrievalError


def _source(
    document_id: str = "doc-1",
    chunk_index: int = 0,
    text: str = "Return within 14 days.",
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
) -> KnowledgeRetrievalContext:
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
        source_count=len(sources),
        total_chars=len(context_text),
        truncated=False,
    )


def _sample_result() -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer="Возврат оформляется в течение 14 дней.",
        citations=(KnowledgeAnswerCitation(1, "doc-1", 0),),
        sufficient_context=True,
    )


class _RecordingContextService:
    """Stub context service that records calls and returns a preset context."""

    def __init__(
        self,
        context: Optional[KnowledgeRetrievalContext] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.context = context
        self.error = error
        self.calls: list[dict[str, object]] = []

    def build_context(
        self,
        db_path: Path,
        *,
        company_id: str,
        query: str,
        retrieval_limit: Optional[int] = None,
        options: Optional[KnowledgeContextBuildingOptions] = None,
    ) -> KnowledgeRetrievalContext:
        self.calls.append(
            {
                "db_path": db_path,
                "company_id": company_id,
                "query": query,
                "retrieval_limit": retrieval_limit,
                "options": options,
            }
        )
        if self.error is not None:
            raise self.error
        if self.context is not None:
            return self.context
        return _context(query=query)


class _RecordingAnswerService:
    """Stub answer service that records requests and returns a preset result."""

    def __init__(
        self,
        result: Optional[KnowledgeAnswerResult] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.result = result if result is not None else _sample_result()
        self.error = error
        self.calls: list[KnowledgeAnswerRequest] = []

    def answer(self, request: KnowledgeAnswerRequest) -> KnowledgeAnswerResult:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class KnowledgeQuestionAnsweringServiceSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        self.source = _source()
        self.context = _context(sources=(self.source,))
        self.expected_result = _sample_result()
        self.context_service = _RecordingContextService(context=self.context)
        self.answer_service = _RecordingAnswerService(result=self.expected_result)
        self.service = KnowledgeQuestionAnsweringService(
            context_service=self.context_service,
            answer_service=self.answer_service,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_context_service_called_exactly_once(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Как оформить возврат?",
        )

        self.assertEqual(len(self.context_service.calls), 1)

    def test_answer_service_called_exactly_once(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Как оформить возврат?",
        )

        self.assertEqual(len(self.answer_service.calls), 1)

    def test_context_passed_into_answer_request(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Как оформить возврат?",
        )

        request = self.answer_service.calls[0]
        self.assertIs(request.context, self.context)

    def test_original_question_preserved(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Как оформить возврат?",
        )

        self.assertEqual(
            self.answer_service.calls[0].question,
            "Как оформить возврат?",
        )

    def test_language_preserved(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
            language="kk",
        )

        self.assertEqual(self.answer_service.calls[0].language, "kk")

    def test_db_path_forwarded(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
        )

        self.assertIs(self.context_service.calls[0]["db_path"], self.db_path)

    def test_company_id_forwarded(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
        )

        self.assertEqual(self.context_service.calls[0]["company_id"], "company-a")

    def test_retrieval_limit_forwarded(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
            retrieval_limit=7,
        )

        self.assertEqual(self.context_service.calls[0]["retrieval_limit"], 7)

    def test_context_options_forwarded(self) -> None:
        options = KnowledgeContextBuildingOptions(max_sources=3)
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
            context_options=options,
        )

        self.assertIs(self.context_service.calls[0]["options"], options)

    def test_returns_answer_service_result(self) -> None:
        result = self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
        )

        self.assertIs(result, self.expected_result)

    def test_call_order_context_then_answer(self) -> None:
        call_log: list[str] = []

        class _OrderedContextService(_RecordingContextService):
            def build_context(self, *args, **kwargs):
                call_log.append("context")
                return super().build_context(*args, **kwargs)

        class _OrderedAnswerService(_RecordingAnswerService):
            def answer(self, request):
                call_log.append("answer")
                return super().answer(request)

        service = KnowledgeQuestionAnsweringService(
            context_service=_OrderedContextService(context=self.context),
            answer_service=_OrderedAnswerService(result=self.expected_result),
        )

        service.answer(
            self.db_path,
            company_id="company-a",
            question="Question",
        )

        self.assertEqual(call_log, ["context", "answer"])


class KnowledgeQuestionAnsweringServiceEmptyContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        self.empty_context = _context(sources=(), context_text="")
        self.context_service = _RecordingContextService(context=self.empty_context)
        self.answer_service = _RecordingAnswerService()
        self.service = KnowledgeQuestionAnsweringService(
            context_service=self.context_service,
            answer_service=self.answer_service,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_empty_context_still_passed_to_answer_service(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Unknown topic",
        )

        self.assertEqual(len(self.answer_service.calls), 1)
        self.assertIs(self.answer_service.calls[0].context, self.empty_context)
        self.assertEqual(self.answer_service.calls[0].context.source_count, 0)

    def test_answer_service_still_called_once_for_empty_context(self) -> None:
        self.service.answer(
            self.db_path,
            company_id="company-a",
            question="Unknown topic",
        )

        self.assertEqual(len(self.answer_service.calls), 1)

    def test_service_does_not_invent_fallback_text(self) -> None:
        empty_result = KnowledgeAnswerResult(
            answer="Недостаточно корпоративных данных.",
            citations=(),
            sufficient_context=False,
        )
        answer_service = _RecordingAnswerService(result=empty_result)
        service = KnowledgeQuestionAnsweringService(
            context_service=self.context_service,
            answer_service=answer_service,
        )

        result = service.answer(
            self.db_path,
            company_id="company-a",
            question="Unknown topic",
        )

        self.assertIs(result, empty_result)


class KnowledgeQuestionAnsweringServiceErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_context_service_failure_wrapped(self) -> None:
        original = KnowledgeRetrievalError("query must not be empty")
        context_service = _RecordingContextService(error=original)
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        with self.assertRaises(KnowledgeQuestionAnsweringError) as ctx:
            service.answer(
                self.db_path,
                company_id="company-a",
                question="   ",
            )

        self.assertEqual(
            ctx.exception.message,
            "Failed to build knowledge answer context.",
        )
        self.assertIs(ctx.exception.__cause__, original)

    def test_answer_service_failure_wrapped(self) -> None:
        original = KnowledgeAnswerGenerationError("Invalid JSON response.")
        context_service = _RecordingContextService(context=_context())
        answer_service = _RecordingAnswerService(error=original)
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        with self.assertRaises(KnowledgeQuestionAnsweringError) as ctx:
            service.answer(
                self.db_path,
                company_id="company-a",
                question="Question",
            )

        self.assertEqual(
            ctx.exception.message,
            "Failed to generate grounded knowledge answer.",
        )
        self.assertIs(ctx.exception.__cause__, original)

    def test_context_building_error_wrapped(self) -> None:
        original = KnowledgeContextBuildingError("query must not be empty")
        context_service = _RecordingContextService(error=original)
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        with self.assertRaises(KnowledgeQuestionAnsweringError) as ctx:
            service.answer(
                self.db_path,
                company_id="company-a",
                question="   ",
            )

        self.assertEqual(
            ctx.exception.message,
            "Failed to build knowledge answer context.",
        )
        self.assertIs(ctx.exception.__cause__, original)

    def test_answer_service_not_called_when_retrieval_fails(self) -> None:
        context_service = _RecordingContextService(
            error=KnowledgeRetrievalError("query must not be empty"),
        )
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        with self.assertRaises(KnowledgeQuestionAnsweringError):
            service.answer(
                self.db_path,
                company_id="company-a",
                question="   ",
            )

        self.assertEqual(len(answer_service.calls), 0)

    def test_answer_service_not_called_when_context_building_fails(self) -> None:
        context_service = _RecordingContextService(
            error=KnowledgeContextBuildingError("query must not be empty"),
        )
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        with self.assertRaises(KnowledgeQuestionAnsweringError):
            service.answer(
                self.db_path,
                company_id="company-a",
                question="   ",
            )

        self.assertEqual(len(answer_service.calls), 0)

    def test_unexpected_context_error_propagates_unchanged(self) -> None:
        context_service = _RecordingContextService(
            error=RuntimeError("unexpected programming defect"),
        )
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        with self.assertRaises(RuntimeError) as ctx:
            service.answer(
                self.db_path,
                company_id="company-a",
                question="Question",
            )

        self.assertEqual(str(ctx.exception), "unexpected programming defect")
        self.assertEqual(len(answer_service.calls), 0)


class KnowledgeQuestionAnsweringServiceBoundaryTests(unittest.TestCase):
    def test_service_does_not_call_retrieval_repository_directly(self) -> None:
        context_service = _RecordingContextService(context=_context())
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        self.assertFalse(hasattr(service, "_retrieval_service"))
        self.assertFalse(hasattr(service, "_provider"))

    def test_dependencies_are_injected(self) -> None:
        context_service = _RecordingContextService()
        answer_service = _RecordingAnswerService()
        service = KnowledgeQuestionAnsweringService(
            context_service=context_service,
            answer_service=answer_service,
        )

        self.assertIs(service._context_service, context_service)
        self.assertIs(service._answer_service, answer_service)


if __name__ == "__main__":
    unittest.main()
