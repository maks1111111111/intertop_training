"""Tests for OpenAI grounded Knowledge Base answer wiring."""

from __future__ import annotations

import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from app.ai.config import OpenAIConfig
from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerAI,
    KnowledgeAnswerCitation,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_prompt_builder import KnowledgeAnswerPromptBuilder
from app.ai.knowledge_answer_response_parser import KnowledgeAnswerResponseParser
from app.ai.knowledge_answer_service import (
    KnowledgeAnswerGenerationError,
    KnowledgeAnswerService,
)
from app.ai.knowledge_answer_validator import KnowledgeAnswerValidator
from app.ai.openai_knowledge_answer_provider import (
    OpenAIKnowledgeAnswerAI,
    create_knowledge_answer_service_from_config,
)
from app.knowledge.context_builder import (
    KnowledgeContextSource,
    KnowledgeRetrievalContext,
)


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


def _sample_request() -> KnowledgeAnswerRequest:
    source = _source()
    return KnowledgeAnswerRequest(
        question="Как оформить возврат?",
        context=_context(sources=(source,)),
        language="ru",
    )


def _sample_result() -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer="Возврат оформляется в течение 14 дней.",
        citations=(KnowledgeAnswerCitation(1, "doc-1", 0),),
        sufficient_context=True,
    )


class CreateKnowledgeAnswerServiceFromConfigTests(unittest.TestCase):
    """Tests for :func:`create_knowledge_answer_service_from_config`."""

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_creates_openai_client_when_client_omitted(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance

        service = create_knowledge_answer_service_from_config(config)

        mock_openai_client_class.assert_called_once_with(config)
        self.assertIs(service._provider, mock_client_instance)

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_uses_injected_client(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        injected_client = MagicMock()

        service = create_knowledge_answer_service_from_config(
            config,
            client=injected_client,
        )

        mock_openai_client_class.assert_not_called()
        self.assertIs(service._provider, injected_client)

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_returns_knowledge_answer_service(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_openai_client_class.return_value = MagicMock()

        service = create_knowledge_answer_service_from_config(config)

        self.assertIsInstance(service, KnowledgeAnswerService)

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_pipeline_components_owned_by_service(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_openai_client_class.return_value = MagicMock()
        injected_builder = MagicMock()
        injected_parser = MagicMock()
        injected_validator = MagicMock()

        service = create_knowledge_answer_service_from_config(
            config,
            prompt_builder=injected_builder,
            response_parser=injected_parser,
            validator=injected_validator,
        )

        self.assertIs(service._prompt_builder, injected_builder)
        self.assertIs(service._response_parser, injected_parser)
        self.assertIs(service._validator, injected_validator)


class OpenAIKnowledgeAnswerAIAdapterTests(unittest.TestCase):
    """Tests for :class:`OpenAIKnowledgeAnswerAI` thin adapter."""

    def test_stores_model_and_service(self) -> None:
        mock_service = MagicMock(spec=KnowledgeAnswerService)
        adapter = OpenAIKnowledgeAnswerAI(service=mock_service, model="gpt-4o")

        self.assertEqual(adapter._model, "gpt-4o")
        self.assertIs(adapter.service, mock_service)

    def test_answer_delegates_to_service(self) -> None:
        mock_service = MagicMock(spec=KnowledgeAnswerService)
        expected_result = _sample_result()
        mock_service.answer.return_value = expected_result
        adapter = OpenAIKnowledgeAnswerAI(service=mock_service, model="gpt-4o")
        request = _sample_request()

        result = adapter.answer(request)

        mock_service.answer.assert_called_once_with(request)
        self.assertIs(result, expected_result)

    def test_answer_does_not_call_provider_directly(self) -> None:
        mock_provider = MagicMock()
        mock_service = KnowledgeAnswerService(provider=mock_provider)
        adapter = OpenAIKnowledgeAnswerAI(service=mock_service, model="gpt-4o")

        with patch.object(
            mock_service,
            "answer",
            wraps=mock_service.answer,
        ) as wrapped_answer:
            with patch.object(
                mock_service._prompt_builder,
                "build",
                side_effect=KnowledgeAnswerGenerationError("blocked"),
            ):
                with self.assertRaises(KnowledgeAnswerGenerationError):
                    adapter.answer(_sample_request())

        wrapped_answer.assert_called_once()
        mock_provider.generate.assert_not_called()

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_from_config_wires_service_with_openai_client(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance

        adapter = OpenAIKnowledgeAnswerAI.from_config(config)

        mock_openai_client_class.assert_called_once_with(config)
        self.assertEqual(adapter._model, "gpt-4o")
        self.assertIs(adapter.service._provider, mock_client_instance)

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_from_config_uses_injected_client(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        injected_client = MagicMock()

        adapter = OpenAIKnowledgeAnswerAI.from_config(
            config,
            client=injected_client,
        )

        mock_openai_client_class.assert_not_called()
        self.assertIs(adapter.service._provider, injected_client)

    @patch("app.ai.openai_knowledge_answer_provider.OpenAIClient")
    def test_from_config_passes_pipeline_overrides_to_service(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_openai_client_class.return_value = MagicMock()
        injected_builder = MagicMock()
        injected_parser = MagicMock()
        injected_validator = MagicMock()

        adapter = OpenAIKnowledgeAnswerAI.from_config(
            config,
            prompt_builder=injected_builder,
            response_parser=injected_parser,
            validator=injected_validator,
        )

        self.assertIs(adapter.service._prompt_builder, injected_builder)
        self.assertIs(adapter.service._response_parser, injected_parser)
        self.assertIs(adapter.service._validator, injected_validator)


class OpenAIKnowledgeAnswerAIPipelineOwnershipTests(unittest.TestCase):
    """Tests proving the adapter does not duplicate the answer pipeline."""

    def test_service_prompt_builder_used_for_answer(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            '{"answer":"ok","sufficient_context":true,'
            '"citations":[{"source_number":1,'
            '"document_id":"doc-1","chunk_index":0}]}'
        )
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Knowledge prompt."
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _sample_result()
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )
        adapter = OpenAIKnowledgeAnswerAI(service=service, model="gpt-4o")
        request = _sample_request()

        adapter.answer(request)

        mock_prompt_builder.build.assert_called_once_with(request)
        mock_provider.generate.assert_called_once_with("Knowledge prompt.")
        mock_parser.parse.assert_called_once()
        mock_validator.validate.assert_called_once_with(
            _sample_result(),
            request.context,
        )

    def test_no_duplicate_pipeline_on_adapter(self) -> None:
        adapter = OpenAIKnowledgeAnswerAI(
            service=MagicMock(spec=KnowledgeAnswerService),
            model="gpt-4o",
        )

        self.assertFalse(hasattr(adapter, "_prompt_builder"))
        self.assertFalse(hasattr(adapter, "_response_parser"))
        self.assertFalse(hasattr(adapter, "_validator"))
        self.assertFalse(hasattr(adapter, "_client"))


class OpenAIKnowledgeAnswerAIGroundingTests(unittest.TestCase):
    """Tests for grounding through :class:`KnowledgeAnswerService`."""

    def test_invalid_citation_rejected_by_service_validator(self) -> None:
        source = _source(document_id="policy-a", chunk_index=0)
        request = KnowledgeAnswerRequest(
            question="What is the policy?",
            context=_context(sources=(source,)),
            language="en",
        )
        hallucinated_json = (
            '{"answer":"The policy allows everything.",'
            '"sufficient_context":true,'
            '"citations":[{"source_number":1,'
            '"document_id":"other-doc","chunk_index":0}]}'
        )
        mock_provider = MagicMock()
        mock_provider.generate.return_value = hallucinated_json
        service = KnowledgeAnswerService(
            provider=mock_provider,
            validator=KnowledgeAnswerValidator(),
        )
        adapter = OpenAIKnowledgeAnswerAI(service=service, model="gpt-4o")

        with self.assertRaises(KnowledgeAnswerGenerationError):
            adapter.answer(request)

    def test_empty_context_sufficient_context_true_rejected(self) -> None:
        request = KnowledgeAnswerRequest(
            question="What is the policy?",
            context=_context(),
            language="en",
        )
        invalid_json = (
            '{"answer":"The policy is clear.",'
            '"sufficient_context":true,'
            '"citations":[]}'
        )
        mock_provider = MagicMock()
        mock_provider.generate.return_value = invalid_json
        service = KnowledgeAnswerService(
            provider=mock_provider,
            validator=KnowledgeAnswerValidator(),
        )
        adapter = OpenAIKnowledgeAnswerAI(service=service, model="gpt-4o")

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            adapter.answer(request)

        self.assertIn("empty context", context.exception.message)

    def test_successful_grounded_answer_returned(self) -> None:
        source = _source(document_id="policy-a", chunk_index=3)
        request = KnowledgeAnswerRequest(
            question="What is the return window?",
            context=_context(sources=(source,)),
            language="en",
        )
        valid_json = (
            '{"answer":"Returns are accepted within 14 days.",'
            '"sufficient_context":true,'
            '"citations":[{"source_number":1,'
            '"document_id":"policy-a","chunk_index":3}]}'
        )
        mock_provider = MagicMock()
        mock_provider.generate.return_value = valid_json
        service = KnowledgeAnswerService(provider=mock_provider)
        adapter = OpenAIKnowledgeAnswerAI(service=service, model="gpt-4o")

        result = adapter.answer(request)

        self.assertEqual(result.answer, "Returns are accepted within 14 days.")
        self.assertEqual(result.citations, (KnowledgeAnswerCitation(1, "policy-a", 3),))
        self.assertTrue(result.sufficient_context)


class OpenAIKnowledgeAnswerAIErrorBoundaryTests(unittest.TestCase):
    """Tests for error wrapping via :class:`KnowledgeAnswerService`."""

    def test_service_failure_wrapped_as_generation_error(self) -> None:
        mock_service = MagicMock(spec=KnowledgeAnswerService)
        mock_service.answer.side_effect = KnowledgeAnswerGenerationError(
            "Failed to generate knowledge answer."
        )
        adapter = OpenAIKnowledgeAnswerAI(service=mock_service, model="gpt-4o")

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            adapter.answer(_sample_request())

        self.assertEqual(
            context.exception.message,
            "Failed to generate knowledge answer.",
        )

    def test_provider_failure_does_not_bypass_service(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("Client failed.")
        service = KnowledgeAnswerService(provider=mock_provider)
        adapter = OpenAIKnowledgeAnswerAI(service=service, model="gpt-4o")

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            adapter.answer(_sample_request())

        self.assertEqual(
            context.exception.message,
            "Failed to generate knowledge answer.",
        )
        self.assertIsInstance(context.exception.__cause__, RuntimeError)


class OpenAIKnowledgeAnswerAIProtocolTests(unittest.TestCase):
    """Tests for :class:`KnowledgeAnswerAI` protocol compatibility."""

    def test_can_be_assigned_to_knowledge_answer_ai_variable(self) -> None:
        mock_service = MagicMock(spec=KnowledgeAnswerService)
        expected_result = _sample_result()
        mock_service.answer.return_value = expected_result
        adapter: KnowledgeAnswerAI = OpenAIKnowledgeAnswerAI(
            service=mock_service,
            model="gpt-4o",
        )

        result = adapter.answer(_sample_request())

        self.assertIs(result, expected_result)


if __name__ == "__main__":
    unittest.main()
