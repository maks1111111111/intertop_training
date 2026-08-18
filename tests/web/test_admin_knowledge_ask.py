"""Tests for the admin Knowledge Base grounded Q&A Web page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity

from app.web.admin_knowledge_question_service import (
    AdminKnowledgeAnswerSource,
    AdminKnowledgeAnswerSourceGroup,
    AdminKnowledgeAnswerView,
    AdminKnowledgeQuestionError,
    AdminKnowledgeQuestionService,
)
from tests.web.test_web_ui import _create_test_app


class _RecordingQuestionService:
    """Fake AdminKnowledgeQuestionService for route tests."""

    def __init__(
        self,
        *,
        result: Optional[AdminKnowledgeAnswerView] = None,
        error: Optional[AdminKnowledgeQuestionError] = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, str]] = []

    def answer_question(
        self,
        company_id: str,
        question: str,
        language: str = "ru",
    ) -> AdminKnowledgeAnswerView:
        self.calls.append(
            {
                "company_id": company_id,
                "question": question,
                "language": language,
            }
        )
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("result must be set when no error is configured")
        return self.result


def _success_view(
    *,
    question: str = "Как оформить возврат?",
    answer: str = "Возврат оформляется в течение 14 дней.",
    sufficient_context: bool = True,
    sources: tuple[AdminKnowledgeAnswerSource, ...] = (
        AdminKnowledgeAnswerSource(
            source_number=1,
            document_id="doc-a",
            chunk_index=0,
            title="Return Policy",
            original_filename="returns.pdf",
        ),
        AdminKnowledgeAnswerSource(
            source_number=2,
            document_id="doc-b",
            chunk_index=3,
            title="Customer Service",
            original_filename="service.docx",
        ),
    ),
    source_groups: Optional[tuple[AdminKnowledgeAnswerSourceGroup, ...]] = None,
) -> AdminKnowledgeAnswerView:
    if source_groups is None:
        source_groups = (
            AdminKnowledgeAnswerSourceGroup(
                document_id="doc-a",
                title="Return Policy",
                original_filename="returns.pdf",
                view_url="/admin/knowledge/doc-a",
                excerpts=(),
                fragment_count=1,
            ),
            AdminKnowledgeAnswerSourceGroup(
                document_id="doc-b",
                title="Customer Service",
                original_filename="service.docx",
                view_url="/admin/knowledge/doc-b",
                excerpts=(),
                fragment_count=1,
            ),
        )
    return AdminKnowledgeAnswerView(
        question=question,
        answer=answer,
        sufficient_context=sufficient_context,
        sources=sources,
        source_groups=source_groups,
    )


class AdminKnowledgeAskPageTests(unittest.TestCase):
    """Verify the admin Knowledge Base grounded Q&A page."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.fake_service = _RecordingQuestionService()
        self.app.state.admin_knowledge_question_service = self.fake_service
        self.client = TestClient(self.app)
        self.app.dependency_overrides[get_current_web_identity] = lambda: WebIdentity(
            user_id=10,
            telegram_id=None,
            company_id="intertop",
            company_name="Intertop Retail",
            role="admin",
        )

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_ask_page_returns_200(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertEqual(response.status_code, 200)

    def test_ask_page_shows_ai_assistant_title(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn("AI-помощник по базе знаний", response.text)

    def test_ask_page_shows_empty_welcome_state(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        html = response.text
        self.assertIn("ai-chat-empty", html)
        self.assertIn(
            "Здравствуйте! Я помогу найти информацию в корпоративной базе знаний.",
            html,
        )

    def test_ask_page_shows_question_textarea(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn('name="question"', response.text)

    def test_ask_page_shows_composer_placeholder(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn(
            'placeholder="Спросите что-нибудь о корпоративных документах..."',
            response.text,
        )

    def test_ask_page_shows_submit_button(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn("ai-chat-composer-submit-label", response.text)
        self.assertIn(">Отправить</span>", response.text)

    def test_ask_page_shows_language_selector(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        html = response.text
        self.assertIn('name="language"', html)
        self.assertIn(">Русский</option>", html)
        self.assertIn(">Қазақша</option>", html)
        self.assertIn(">English</option>", html)

    def test_ask_page_explains_published_documents_are_used(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn("опубликованной базы знаний", response.text)

    def test_knowledge_page_links_to_ask_page(self) -> None:
        response = self.client.get("/admin/knowledge")

        self.assertIn('href="/admin/knowledge/ask"', response.text)
        self.assertIn("Задать вопрос", response.text)

    def test_ask_page_marks_subnav_as_active(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn(
            'href="/admin/knowledge" class="admin-subnav-link is-active"',
            response.text,
        )
        self.assertNotIn("admin-subnav-linkis-active", response.text)

    def test_ask_page_presentation_copy_regressions(self) -> None:
        """Guard against missing spaces in subnav class and welcome/example copy."""
        response = self.client.get("/admin/knowledge/ask")
        html = response.text

        self.assertIn('class="admin-subnav-link is-active"', html)
        self.assertNotIn("admin-subnav-linkis-active", html)
        self.assertIn(
            "Здравствуйте! Я помогу найти информацию в корпоративной базе знаний.",
            html,
        )
        self.assertNotIn("информациюв", html)
        self.assertIn("Где найти инструкцию по открытию смены?", html)
        self.assertNotIn("найтиинструкцию", html)

    def test_ask_page_title_uses_intertop_training_brand(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        self.assertIn("Intertop Training", response.text)
        self.assertNotIn("IntertopTraining", response.text)
        self.assertIn(
            "<title>AI-помощник — База знаний — Intertop Training</title>",
            response.text,
        )

    def test_post_forwards_question_and_language_to_service(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={
                "question": "  Как оформить возврат?  ",
                "language": "kk",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.fake_service.calls), 1)
        self.assertEqual(self.fake_service.calls[0]["company_id"], "intertop")
        self.assertEqual(
            self.fake_service.calls[0]["question"],
            "  Как оформить возврат?  ",
        )
        self.assertEqual(self.fake_service.calls[0]["language"], "kk")

    def test_post_success_renders_answer_text(self) -> None:
        self.fake_service.result = _success_view(
            answer="Возврат оформляется в течение 14 дней.",
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI-помощник", response.text)
        self.assertIn("Возврат оформляется в течение 14 дней.", response.text)

    def test_post_success_renders_user_message_as_chat_bubble(self) -> None:
        self.fake_service.result = _success_view(
            question="Какие стандарты обслуживания существуют?",
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={
                "question": "Какие стандарты обслуживания существуют?",
                "language": "ru",
            },
        )

        html = response.text
        self.assertIn("ai-chat-message--user", html)
        self.assertIn("Какие стандарты обслуживания существуют?", html)

    def test_post_success_renders_assistant_chat_message(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        html = response.text
        self.assertIn("ai-chat-message--assistant", html)
        self.assertIn("ai-chat-assistant-label", html)

    def test_post_success_renders_sufficient_context_state(self) -> None:
        self.fake_service.result = _success_view(sufficient_context=True)

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertNotIn(
            "Недостаточно информации в опубликованных документах.",
            response.text,
        )
        self.assertNotIn("ai-chat-message--insufficient", response.text)

    def test_post_success_renders_source_title(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn("Return Policy", response.text)
        self.assertIn("Customer Service", response.text)

    def test_post_success_renders_source_original_filename(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn("returns.pdf", response.text)
        self.assertIn("service.docx", response.text)

    def test_post_success_renders_compact_source_cards(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        html = response.text
        self.assertIn("ai-chat-sources", html)
        self.assertIn("ai-chat-source-card", html)

    def test_post_success_does_not_show_source_number_as_primary_label(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertNotRegex(response.text, r"Источник\s+\d+")

    def test_post_success_does_not_render_fake_source_links(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertNotIn('href="#"', response.text)

    def test_post_success_renders_document_open_link(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn('href="/admin/knowledge/doc-a"', response.text)
        self.assertIn("Открыть документ →", response.text)

    def test_post_success_renders_grouped_fragment_count(self) -> None:
        self.fake_service.result = _success_view(
            source_groups=(
                AdminKnowledgeAnswerSourceGroup(
                    document_id="doc-a",
                    title="Return Policy",
                    original_filename="returns.pdf",
                    view_url="/admin/knowledge/doc-a",
                    excerpts=(),
                    fragment_count=2,
                ),
            ),
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn("Использовано фрагментов: 2", response.text)

    def test_post_success_renders_chunk_excerpt(self) -> None:
        from app.web.admin_knowledge_question_service import (
            AdminKnowledgeAnswerChunkExcerpt,
        )

        self.fake_service.result = _success_view(
            source_groups=(
                AdminKnowledgeAnswerSourceGroup(
                    document_id="doc-a",
                    title="Return Policy",
                    original_filename="returns.pdf",
                    view_url="/admin/knowledge/doc-a",
                    excerpts=(
                        AdminKnowledgeAnswerChunkExcerpt(
                            chunk_index=0,
                            excerpt="Активно слушай, проявляй интерес и понимание.",
                        ),
                    ),
                    fragment_count=1,
                ),
            ),
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn("ai-chat-source-excerpt", response.text)
        self.assertIn(
            "Активно слушай, проявляй интерес и понимание.",
            response.text,
        )

    def test_post_success_groups_duplicate_document_citations(self) -> None:
        self.fake_service.result = _success_view(
            sources=(
                AdminKnowledgeAnswerSource(
                    source_number=1,
                    document_id="doc-a",
                    chunk_index=0,
                    title="Return Policy",
                    original_filename="returns.pdf",
                ),
                AdminKnowledgeAnswerSource(
                    source_number=5,
                    document_id="doc-a",
                    chunk_index=4,
                    title="Return Policy",
                    original_filename="returns.pdf",
                ),
            ),
            source_groups=(
                AdminKnowledgeAnswerSourceGroup(
                    document_id="doc-a",
                    title="Return Policy",
                    original_filename="returns.pdf",
                    view_url="/admin/knowledge/doc-a",
                    excerpts=(),
                    fragment_count=2,
                ),
            ),
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        html = response.text
        self.assertEqual(html.count("ai-chat-source-card"), 1)
        self.assertIn("Использовано фрагментов: 2", html)

    def test_post_success_preserves_source_ordering(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        html = response.text
        first_index = html.index("Return Policy")
        second_index = html.index("Customer Service")
        self.assertLess(first_index, second_index)

    def test_post_success_preserves_submitted_question_in_textarea(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn(">Как оформить возврат?<", response.text)

    def test_post_success_preserves_selected_language(self) -> None:
        self.fake_service.result = _success_view()

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "en"},
        )

        self.assertIn('value="en" selected', response.text)

    def test_post_insufficient_context_renders_exact_message(self) -> None:
        self.fake_service.result = _success_view(
            answer="В доступных документах нет достаточной информации.",
            sufficient_context=False,
            sources=(),
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn(
            "Недостаточно информации в опубликованных документах.",
            response.text,
        )
        self.assertIn("ai-chat-message--insufficient", response.text)

    def test_post_insufficient_context_explains_published_only_policy(self) -> None:
        self.fake_service.result = _success_view(
            sufficient_context=False,
            sources=(),
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertIn(
            "AI отвечает только на основании опубликованной базы знаний",
            response.text,
        )

    def test_post_insufficient_context_does_not_render_sources_section(self) -> None:
        self.fake_service.result = _success_view(
            sufficient_context=False,
            sources=(),
        )

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertNotIn("ai-chat-sources", response.text)
        self.assertNotIn("ai-chat-source-card", response.text)

    def test_post_error_renders_safe_message(self) -> None:
        self.fake_service.error = AdminKnowledgeQuestionError("Вопрос обязателен.")

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "   ", "language": "ru"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Вопрос обязателен.", response.text)

    def test_post_error_preserves_question_and_language(self) -> None:
        self.fake_service.error = AdminKnowledgeQuestionError("Вопрос обязателен.")

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "   ", "language": "kk"},
        )

        self.assertIn('value="kk" selected', response.text)

    def test_app_state_service_override_is_respected(self) -> None:
        override = _RecordingQuestionService(result=_success_view(answer="Override answer"))
        self.app.state.admin_knowledge_question_service = override

        response = self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Test question", "language": "ru"},
        )

        self.assertEqual(len(override.calls), 1)
        self.assertEqual(len(self.fake_service.calls), 0)
        self.assertIn("Override answer", response.text)

    @patch("app.web.router.AdminKnowledgeQuestionService")
    @patch("app.web.router.create_knowledge_question_answering_service")
    @patch("app.web.router.OpenAIConfig.from_environment")
    def test_provider_without_override_wires_bootstrap(
        self,
        mock_from_environment,
        mock_create_service,
        mock_service_class,
    ) -> None:
        app, db_tmp, _, upload_tmp = _create_test_app(self.courses_dir)
        self.addCleanup(upload_tmp.cleanup)
        self.addCleanup(db_tmp.cleanup)
        app.dependency_overrides[get_current_web_identity] = lambda: WebIdentity(
            user_id=10,
            telegram_id=None,
            company_id="intertop",
            company_name="Intertop Retail",
            role="admin",
        )
        self.addCleanup(app.dependency_overrides.clear)

        mock_config = object()
        mock_from_environment.return_value = mock_config
        mock_lower_service = object()
        mock_create_service.return_value = mock_lower_service
        mock_service_instance = _RecordingQuestionService(result=_success_view())
        mock_service_class.return_value = mock_service_instance

        client = TestClient(app)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            response = client.post(
                "/admin/knowledge/ask",
                data={"question": "Test question", "language": "ru"},
            )

        self.assertEqual(response.status_code, 200)
        mock_from_environment.assert_called_once()
        mock_create_service.assert_called_once_with(mock_config)
        mock_service_class.assert_called_once()
        _, service_kwargs = mock_service_class.call_args
        self.assertIs(service_kwargs["question_answering_service"], mock_lower_service)
        self.assertEqual(len(mock_service_instance.calls), 1)

    def test_post_invokes_service_exactly_once(self) -> None:
        self.fake_service.result = _success_view()

        self.client.post(
            "/admin/knowledge/ask",
            data={"question": "Как оформить возврат?", "language": "ru"},
        )

        self.assertEqual(len(self.fake_service.calls), 1)

    def test_ask_page_contains_thinking_card_markup(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        html = response.text
        self.assertIn("ai-chat-thinking", html)
        self.assertIn("Поиск информации...", html)
        self.assertIn("анализ документов", html)
        self.assertIn("подготовка ответа", html)

    def test_ask_page_contains_loading_state_markup(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        html = response.text
        self.assertIn('data-loading-label="ИИ анализирует документы..."', html)
        self.assertIn("ai-chat-composer-spinner", html)
        self.assertIn('id="ai-chat-composer"', html)
        self.assertIn("ai-chat-composer-submit-label", html)

    def test_ask_page_submit_keeps_question_field_submittable(self) -> None:
        response = self.client.get("/admin/knowledge/ask")

        html = response.text
        self.assertIn("textarea.readOnly = true", html)
        self.assertNotIn("textarea.disabled = true", html)
        self.assertNotIn("select.disabled = true", html)


if __name__ == "__main__":
    unittest.main()
