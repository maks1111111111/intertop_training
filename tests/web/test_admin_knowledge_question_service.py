"""Tests for AdminKnowledgeQuestionService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.database.db import initialize_database
from app.knowledge.models import KnowledgeDocumentChunkInput, KnowledgeSourceType
from app.knowledge.question_answering_service import KnowledgeQuestionAnsweringError
from app.repositories import knowledge_chunk_repository, knowledge_document_repository
from app.web.admin_knowledge_question_service import (
    AdminKnowledgeAnswerSource,
    AdminKnowledgeAnswerSourceGroup,
    AdminKnowledgeAnswerView,
    AdminKnowledgeQuestionError,
    AdminKnowledgeQuestionService,
)


def _sample_result(
    *,
    answer: str = "Возврат оформляется в течение 14 дней.",
    sufficient_context: bool = True,
    citations: tuple[KnowledgeAnswerCitation, ...] = (
        KnowledgeAnswerCitation(1, "doc-a", 0),
    ),
) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer,
        citations=citations,
        sufficient_context=sufficient_context,
    )


class _RecordingQuestionAnsweringService:
    """Stub that records delegated calls and returns a preset result."""

    def __init__(
        self,
        result: Optional[KnowledgeAnswerResult] = None,
        *,
        error: Optional[Exception] = None,
    ) -> None:
        self.result = result or _sample_result()
        self.error = error
        self.calls: list[dict[str, object]] = []

    def answer(
        self,
        db_path: Path,
        *,
        company_id: str,
        question: str,
        language: str = "ru",
        retrieval_limit=None,
        context_options=None,
    ) -> KnowledgeAnswerResult:
        self.calls.append(
            {
                "db_path": db_path,
                "company_id": company_id,
                "question": question,
                "language": language,
                "retrieval_limit": retrieval_limit,
                "context_options": context_options,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


class AdminKnowledgeQuestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.question_service = _RecordingQuestionAnsweringService()
        self.service = AdminKnowledgeQuestionService(
            self.db_path,
            question_answering_service=self.question_service,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_document(
        self,
        *,
        company_id: str = "company-a",
        title: str = "Return Policy",
        original_filename: str = "returns.pdf",
    ):
        return knowledge_document_repository.create_document(
            self.db_path,
            company_id=company_id,
            title=title,
            original_filename=original_filename,
            source_type=KnowledgeSourceType.PDF,
        )

    def test_empty_question_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question("company-a", "")

        self.assertEqual(ctx.exception.message, "Вопрос обязателен.")
        self.assertEqual(self.question_service.calls, [])

    def test_whitespace_only_question_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question("company-a", "   ")

        self.assertEqual(ctx.exception.message, "Вопрос обязателен.")
        self.assertEqual(self.question_service.calls, [])

    def test_empty_company_id_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question("", "Как оформить возврат?")

        self.assertEqual(
            ctx.exception.message,
            "Идентификатор компании обязателен.",
        )
        self.assertEqual(self.question_service.calls, [])

    def test_whitespace_only_company_id_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question("   ", "Как оформить возврат?")

        self.assertEqual(
            ctx.exception.message,
            "Идентификатор компании обязателен.",
        )

    def test_invalid_language_rejected(self) -> None:
        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question(
                "company-a",
                "Как оформить возврат?",
                language="de",
            )

        self.assertEqual(ctx.exception.message, "Неподдерживаемый язык ответа.")
        self.assertEqual(self.question_service.calls, [])

    def test_company_id_and_question_are_stripped_before_delegation(self) -> None:
        self.service.answer_question(
            "  company-a  ",
            "  Как оформить возврат?  ",
            language=" RU ",
        )

        self.assertEqual(len(self.question_service.calls), 1)
        call = self.question_service.calls[0]
        self.assertEqual(call["company_id"], "company-a")
        self.assertEqual(call["question"], "Как оформить возврат?")
        self.assertEqual(call["language"], "ru")

    def test_successful_answer_maps_answer_text(self) -> None:
        self.question_service.result = _sample_result(
            answer="Ответ по базе знаний.",
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(view.answer, "Ответ по базе знаний.")

    def test_successful_answer_maps_sufficient_context_true(self) -> None:
        self.question_service.result = _sample_result(sufficient_context=True)

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertTrue(view.sufficient_context)

    def test_insufficient_context_maps_sufficient_context_false(self) -> None:
        self.question_service.result = _sample_result(
            answer="Недостаточно информации.",
            sufficient_context=False,
            citations=(),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertFalse(view.sufficient_context)

    def test_no_citations_returns_empty_sources_tuple(self) -> None:
        self.question_service.result = _sample_result(
            answer="Недостаточно информации.",
            sufficient_context=False,
            citations=(),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(view.sources, ())
        self.assertEqual(view.source_groups, ())

    def test_citations_preserve_ordering(self) -> None:
        self.question_service.result = _sample_result(
            citations=(
                KnowledgeAnswerCitation(1, "doc-first", 0),
                KnowledgeAnswerCitation(2, "doc-second", 3),
            ),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(
            [source.document_id for source in view.sources],
            ["doc-first", "doc-second"],
        )
        self.assertEqual(view.sources[0].source_number, 1)
        self.assertEqual(view.sources[1].source_number, 2)
        self.assertEqual(view.sources[1].chunk_index, 3)

    def test_citation_document_metadata_is_enriched(self) -> None:
        document = self._create_document(
            title="Политика возврата",
            original_filename="returns.pdf",
        )
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, document.document_id, 2),),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(len(view.sources), 1)
        source = view.sources[0]
        self.assertIsInstance(source, AdminKnowledgeAnswerSource)
        self.assertEqual(source.title, "Политика возврата")
        self.assertEqual(source.original_filename, "returns.pdf")
        self.assertEqual(source.document_id, document.document_id)
        self.assertEqual(source.chunk_index, 2)

    def test_citation_lookup_is_tenant_scoped(self) -> None:
        own = self._create_document(
            company_id="company-a",
            title="Own Title",
            original_filename="own.pdf",
        )
        other = self._create_document(
            company_id="company-b",
            title="Other Title",
            original_filename="other.pdf",
        )
        self.question_service.result = _sample_result(
            citations=(
                KnowledgeAnswerCitation(1, own.document_id, 0),
                KnowledgeAnswerCitation(2, other.document_id, 0),
            ),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(view.sources[0].title, "Own Title")
        self.assertEqual(view.sources[0].original_filename, "own.pdf")
        self.assertEqual(view.sources[1].title, "")
        self.assertEqual(view.sources[1].original_filename, "")

    def test_missing_citation_document_uses_empty_metadata(self) -> None:
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, "missing-doc", 0),),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(view.sources[0].document_id, "missing-doc")
        self.assertEqual(view.sources[0].title, "")
        self.assertEqual(view.sources[0].original_filename, "")

    def test_knowledge_question_answering_error_is_mapped(self) -> None:
        self.question_service.error = KnowledgeQuestionAnsweringError(
            "Failed to build knowledge answer context."
        )

        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(
            ctx.exception.message,
            "Не удалось получить ответ по базе знаний.",
        )
        self.assertIsInstance(ctx.exception.__cause__, KnowledgeQuestionAnsweringError)

    def test_unexpected_exception_is_mapped(self) -> None:
        self.question_service.error = RuntimeError(
            "sqlite path /secret/db.sqlite exploded"
        )

        with self.assertRaises(AdminKnowledgeQuestionError) as ctx:
            self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(
            ctx.exception.message,
            "Не удалось получить ответ по базе знаний.",
        )
        self.assertNotIn("/secret/", ctx.exception.message)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)

    def test_view_preserves_normalized_question(self) -> None:
        view = self.service.answer_question("company-a", "  Вопрос?  ")

        self.assertEqual(view.question, "Вопрос?")
        self.assertIsInstance(view, AdminKnowledgeAnswerView)

    def test_injected_get_document_dependency_is_used(self) -> None:
        captured: dict[str, str] = {}

        def fake_get_document(
            db_path: Path,
            *,
            company_id: str,
            document_id: str,
        ):
            captured["company_id"] = company_id
            captured["document_id"] = document_id
            return None

        service = AdminKnowledgeQuestionService(
            self.db_path,
            question_answering_service=self.question_service,
            get_document=fake_get_document,
        )
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, "doc-x", 0),),
        )

        service.answer_question("company-a", "Вопрос?")

        self.assertEqual(captured["company_id"], "company-a")
        self.assertEqual(captured["document_id"], "doc-x")

    def test_mock_question_answering_service_receives_db_path(self) -> None:
        mock_service = Mock()
        mock_service.answer.return_value = _sample_result()
        service = AdminKnowledgeQuestionService(
            self.db_path,
            question_answering_service=mock_service,
        )

        service.answer_question("company-a", "Вопрос?")

        mock_service.answer.assert_called_once_with(
            self.db_path,
            company_id="company-a",
            question="Вопрос?",
            language="ru",
        )

    def test_duplicate_document_citations_are_grouped(self) -> None:
        document = self._create_document(title="Standards")
        self.question_service.result = _sample_result(
            citations=(
                KnowledgeAnswerCitation(1, document.document_id, 0),
                KnowledgeAnswerCitation(5, document.document_id, 4),
            ),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(len(view.source_groups), 1)
        group = view.source_groups[0]
        self.assertIsInstance(group, AdminKnowledgeAnswerSourceGroup)
        self.assertEqual(group.document_id, document.document_id)
        self.assertEqual(group.fragment_count, 2)
        self.assertEqual(group.view_url, f"/admin/knowledge/{document.document_id}")
        self.assertEqual(len(view.sources), 2)

    def test_source_group_includes_chunk_excerpt(self) -> None:
        document = self._create_document(title="Standards")
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text="Активно слушай, проявляй интерес и понимание.",
                    start_char=0,
                    end_char=42,
                )
            ],
        )
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, document.document_id, 0),),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(len(view.source_groups), 1)
        self.assertEqual(len(view.source_groups[0].excerpts), 1)
        self.assertIn(
            "Активно слушай",
            view.source_groups[0].excerpts[0].excerpt,
        )

    def test_source_group_tenant_scoped_chunk_lookup(self) -> None:
        own = self._create_document(
            company_id="company-a",
            title="Own",
        )
        other = self._create_document(
            company_id="company-b",
            title="Other",
        )
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=other.company_id,
            document_id=other.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text="Secret other-company chunk text.",
                    start_char=0,
                    end_char=30,
                )
            ],
        )
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, other.document_id, 0),),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(view.source_groups[0].excerpts[0].excerpt, "")
        self.assertEqual(view.sources[0].title, "")

    def test_source_group_skips_ocr_garbage_excerpt(self) -> None:
        document = self._create_document(title="Standards")
        knowledge_chunk_repository.replace_document_chunks(
            self.db_path,
            company_id=document.company_id,
            document_id=document.document_id,
            chunks=[
                KnowledgeDocumentChunkInput(
                    chunk_index=0,
                    text=(
                        "СЕРВИСНЫЕСТАНДАРТЫ\nMadeby\n010203\n"
                        "Активно слушай, проявляй интерес и понимание."
                    ),
                    start_char=0,
                    end_char=80,
                )
            ],
        )
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, document.document_id, 0),),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        excerpt = view.source_groups[0].excerpts[0].excerpt
        self.assertIn("Активно слушай", excerpt)
        self.assertNotIn("Madeby", excerpt)
        self.assertNotIn("010203", excerpt)

    def test_single_fragment_view_url_includes_chunk_query(self) -> None:
        document = self._create_document(title="Standards")
        self.question_service.result = _sample_result(
            citations=(KnowledgeAnswerCitation(1, document.document_id, 4),),
        )

        view = self.service.answer_question("company-a", "Вопрос?")

        self.assertEqual(
            view.source_groups[0].view_url,
            f"/admin/knowledge/{document.document_id}?chunk=4",
        )


if __name__ == "__main__":
    unittest.main()
