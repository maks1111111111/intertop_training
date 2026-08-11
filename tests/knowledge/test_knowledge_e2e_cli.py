"""Tests for Knowledge Base question answering E2E CLI."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.knowledge.e2e_cli import _format_result, run
from app.knowledge.question_answering_service import KnowledgeQuestionAnsweringError


def _sample_result(
    *,
    answer: str = "Возврат оформляется в течение 14 дней.",
    sufficient_context: bool = True,
    citations: tuple[KnowledgeAnswerCitation, ...] = (
        KnowledgeAnswerCitation(1, "doc-1", 0),
    ),
) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer,
        citations=citations,
        sufficient_context=sufficient_context,
    )


class _RecordingQuestionAnsweringService:
    """Stub service that records CLI invocations."""

    instances: list["_RecordingQuestionAnsweringService"] = []

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        _RecordingQuestionAnsweringService.instances.append(self)

    def answer(
        self,
        db_path: Path,
        *,
        company_id: str,
        question: str,
        language: str = "ru",
        retrieval_limit: Optional[int] = None,
        context_options: Optional[object] = None,
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
        return _sample_result()


class FormatResultTests(unittest.TestCase):
    """Tests for CLI result formatting."""

    def test_prints_answer(self) -> None:
        output = _format_result(_sample_result())
        self.assertIn("ANSWER", output)
        self.assertIn("Возврат оформляется в течение 14 дней.", output)

    def test_prints_sufficient_context_true(self) -> None:
        output = _format_result(_sample_result(sufficient_context=True))
        self.assertIn("SUFFICIENT_CONTEXT", output)
        self.assertIn("true", output)

    def test_prints_sufficient_context_false(self) -> None:
        output = _format_result(
            _sample_result(
                answer="Недостаточно информации.",
                sufficient_context=False,
                citations=(),
            )
        )
        self.assertIn("false", output)

    def test_prints_citations(self) -> None:
        output = _format_result(_sample_result())
        self.assertIn("CITATIONS", output)
        self.assertIn("source_number=1", output)
        self.assertIn("document_id=doc-1", output)
        self.assertIn("chunk_index=0", output)

    def test_empty_citations_prints_none_marker(self) -> None:
        output = _format_result(
            _sample_result(
                sufficient_context=False,
                citations=(),
            )
        )
        self.assertIn("(none)", output)


class KnowledgeE2ECliTests(unittest.TestCase):
    """Integration-style tests for the E2E CLI."""

    def setUp(self) -> None:
        _RecordingQuestionAnsweringService.instances.clear()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "training.db"
        self.db_path.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _base_args(self) -> list[str]:
        return [
            "--db",
            str(self.db_path),
            "--company-id",
            "company-a",
            "--question",
            "Как оформить возврат?",
        ]

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_successful_result_prints_answer(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = run(self._base_args())

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("ANSWER", output)
        self.assertIn("Возврат оформляется в течение 14 дней.", output)

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_default_language_is_ru(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        run(self._base_args())

        self.assertEqual(len(service.calls), 1)
        self.assertEqual(service.calls[0]["language"], "ru")

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_explicit_kk_language_forwarded(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        run(self._base_args() + ["--language", "kk"])

        self.assertEqual(service.calls[0]["language"], "kk")

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_explicit_en_language_forwarded(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        run(self._base_args() + ["--language", "en"])

        self.assertEqual(service.calls[0]["language"], "en")

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_retrieval_limit_forwarded(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        run(self._base_args() + ["--retrieval-limit", "7"])

        self.assertEqual(service.calls[0]["retrieval_limit"], 7)

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_service_invoked_exactly_once(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        run(self._base_args())

        mock_create_service.assert_called_once()
        self.assertEqual(len(service.calls), 1)

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_question_answering_error_returns_non_zero_exit_code(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = MagicMock()
        service.answer.side_effect = KnowledgeQuestionAnsweringError(
            "Failed to generate grounded knowledge answer."
        )
        mock_create_service.return_value = service

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = run(self._base_args())

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "Failed to generate grounded knowledge answer.",
            stderr.getvalue(),
        )

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_missing_api_key_returns_non_zero_without_leaking_secret(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        mock_from_environment.side_effect = RuntimeError(
            "OPENAI_API_KEY environment variable is not set."
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = run(self._base_args())

        self.assertEqual(exit_code, 1)
        self.assertNotIn("sk-", stdout.getvalue())
        self.assertNotIn("sk-", stderr.getvalue())
        mock_create_service.assert_not_called()

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_cli_does_not_call_openai_client_directly(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        with patch("app.ai.openai_client.OpenAIClient") as mock_openai_client:
            run(self._base_args())

        mock_openai_client.assert_not_called()

    @patch("app.knowledge.e2e_cli.create_knowledge_question_answering_service")
    @patch("app.knowledge.e2e_cli.OpenAIConfig.from_environment")
    def test_cli_does_not_access_knowledge_repositories_directly(
        self,
        mock_from_environment: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        service = _RecordingQuestionAnsweringService()
        mock_create_service.return_value = service

        with patch(
            "app.repositories.knowledge_chunk_repository.list_for_company"
        ) as mock_list_chunks, patch(
            "app.repositories.knowledge_document_repository.list_for_company"
        ) as mock_list_documents:
            run(self._base_args())

        mock_list_chunks.assert_not_called()
        mock_list_documents.assert_not_called()

    def test_missing_database_returns_non_zero(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = run(
                [
                    "--db",
                    "/nonexistent/training.db",
                    "--company-id",
                    "company-a",
                    "--question",
                    "test",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("database file does not exist", stderr.getvalue())

    def test_invalid_retrieval_limit_returns_non_zero(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = run(self._base_args() + ["--retrieval-limit", "0"])

        self.assertEqual(exit_code, 2)
        self.assertIn("positive integer", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
