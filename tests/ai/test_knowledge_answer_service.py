"""Tests for grounded Knowledge Base answer orchestration service."""

from __future__ import annotations

import unittest
from typing import Optional
from unittest.mock import MagicMock

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_prompt_builder import (
    KnowledgeAnswerPromptBuilder,
    KnowledgeAnswerPromptBuildingError,
)
from app.ai.knowledge_answer_response_parser import (
    KnowledgeAnswerResponseParser,
    KnowledgeAnswerResponseParsingError,
)
from app.ai.knowledge_answer_service import (
    KnowledgeAnswerGenerationError,
    KnowledgeAnswerService,
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


class KnowledgeAnswerServiceSuccessTests(unittest.TestCase):
    """Tests for successful answer generation."""

    def test_answer_returns_validated_result(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = '{"answer":"ok"}'
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt text."
        expected_result = _sample_result()
        mock_parser = MagicMock()
        mock_parser.parse.return_value = expected_result
        mock_validator = MagicMock()
        mock_validator.validate.return_value = expected_result
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )
        request = _sample_request()

        result = service.answer(request)

        self.assertIs(result, expected_result)

    def test_prompt_builder_called_once(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
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
        request = _sample_request()

        service.answer(request)

        mock_prompt_builder.build.assert_called_once_with(request)

    def test_provider_called_once(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        expected_prompt = "Knowledge prompt."
        mock_prompt_builder.build.return_value = expected_prompt
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

        service.answer(_sample_request())

        mock_provider.generate.assert_called_once_with(expected_prompt)

    def test_parser_called_once(self) -> None:
        mock_provider = MagicMock()
        raw_response = '{"answer":"text","sufficient_context":true,"citations":[]}'
        mock_provider.generate.return_value = raw_response
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
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

        service.answer(_sample_request())

        mock_parser.parse.assert_called_once_with(raw_response)

    def test_validator_called_once_with_context(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
        parsed_result = _sample_result()
        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_result
        mock_validator = MagicMock()
        mock_validator.validate.return_value = parsed_result
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )
        request = _sample_request()

        service.answer(request)

        mock_validator.validate.assert_called_once_with(
            parsed_result,
            request.context,
        )

    def test_components_called_in_order(self) -> None:
        call_order: list[str] = []
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = (
            lambda prompt: call_order.append("provider") or "response"
        )
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.side_effect = (
            lambda request: call_order.append("prompt_builder") or "prompt"
        )
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = (
            lambda response: call_order.append("parser") or _sample_result()
        )
        mock_validator = MagicMock()
        mock_validator.validate.side_effect = (
            lambda result, context: call_order.append("validator") or result
        )
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        service.answer(_sample_request())

        self.assertEqual(
            call_order,
            ["prompt_builder", "provider", "parser", "validator"],
        )

    def test_no_duplicate_provider_call(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
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

        service.answer(_sample_request())

        self.assertEqual(mock_provider.generate.call_count, 1)


class KnowledgeAnswerServiceDependencyInjectionTests(unittest.TestCase):
    """Tests for constructor dependency wiring."""

    def test_injected_dependencies_are_stored(self) -> None:
        mock_provider = MagicMock()
        mock_prompt_builder = MagicMock()
        mock_parser = MagicMock()
        mock_validator = MagicMock()
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        self.assertIs(service._provider, mock_provider)
        self.assertIs(service._prompt_builder, mock_prompt_builder)
        self.assertIs(service._response_parser, mock_parser)
        self.assertIs(service._validator, mock_validator)

    def test_default_prompt_builder_type(self) -> None:
        service = KnowledgeAnswerService(provider=MagicMock())

        self.assertIsInstance(
            service._prompt_builder,
            KnowledgeAnswerPromptBuilder,
        )

    def test_default_response_parser_type(self) -> None:
        service = KnowledgeAnswerService(provider=MagicMock())

        self.assertIsInstance(
            service._response_parser,
            KnowledgeAnswerResponseParser,
        )

    def test_default_validator_type(self) -> None:
        service = KnowledgeAnswerService(provider=MagicMock())

        self.assertIsInstance(service._validator, KnowledgeAnswerValidator)

    def test_custom_dependencies_are_used(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Custom prompt."
        expected_result = _sample_result()
        mock_parser = MagicMock()
        mock_parser.parse.return_value = expected_result
        mock_validator = MagicMock()
        mock_validator.validate.return_value = expected_result
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        result = service.answer(_sample_request())

        self.assertIs(result, expected_result)
        mock_prompt_builder.build.assert_called_once()
        mock_provider.generate.assert_called_once_with("Custom prompt.")
        mock_parser.parse.assert_called_once_with("response")
        mock_validator.validate.assert_called_once()


class KnowledgeAnswerServiceFailureTests(unittest.TestCase):
    """Tests for wrapped pipeline failures."""

    def test_provider_failure_wrapped(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("OpenAI API error.")
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
        mock_parser = MagicMock()
        mock_validator = MagicMock()
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(_sample_request())

        self.assertEqual(
            context.exception.message,
            "Failed to generate knowledge answer.",
        )
        self.assertIsInstance(context.exception.__cause__, RuntimeError)
        mock_parser.parse.assert_not_called()
        mock_validator.validate.assert_not_called()

    def test_parser_failure_wrapped(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "not json"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = KnowledgeAnswerResponseParsingError(
            "Response must be valid JSON."
        )
        mock_validator = MagicMock()
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(_sample_request())

        self.assertEqual(
            context.exception.message,
            "Response must be valid JSON.",
        )
        self.assertIsInstance(
            context.exception.__cause__,
            KnowledgeAnswerResponseParsingError,
        )
        mock_validator.validate.assert_not_called()

    def test_validator_failure_wrapped(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.side_effect = KnowledgeAnswerValidationError(
            "Knowledge answer requires at least one valid citation."
        )
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(_sample_request())

        self.assertEqual(
            context.exception.message,
            "Knowledge answer requires at least one valid citation.",
        )
        self.assertIsInstance(
            context.exception.__cause__,
            KnowledgeAnswerValidationError,
        )

    def test_prompt_builder_failure_wrapped(self) -> None:
        mock_provider = MagicMock()
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.side_effect = KnowledgeAnswerPromptBuildingError(
            "Question must not be empty."
        )
        mock_parser = MagicMock()
        mock_validator = MagicMock()
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(_sample_request())

        self.assertEqual(context.exception.message, "Question must not be empty.")
        self.assertIsInstance(
            context.exception.__cause__,
            KnowledgeAnswerPromptBuildingError,
        )
        mock_provider.generate.assert_not_called()
        mock_parser.parse.assert_not_called()
        mock_validator.validate.assert_not_called()

    def test_generation_error_not_rewrapped(self) -> None:
        mock_provider = MagicMock()
        original = KnowledgeAnswerGenerationError("Already wrapped.")
        mock_provider.generate.side_effect = original
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
        )

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(_sample_request())

        self.assertIs(context.exception, original)

    def test_empty_answer_never_bypasses_validator(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Prompt."
        empty_answer_result = KnowledgeAnswerResult(
            answer=" ",
            citations=(),
            sufficient_context=False,
        )
        mock_parser = MagicMock()
        mock_parser.parse.return_value = empty_answer_result
        mock_validator = MagicMock()
        mock_validator.validate.side_effect = KnowledgeAnswerValidationError(
            "Knowledge answer must not be empty."
        )
        service = KnowledgeAnswerService(
            provider=mock_provider,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(_sample_request())

        mock_validator.validate.assert_called_once_with(
            empty_answer_result,
            _sample_request().context,
        )
        self.assertEqual(
            context.exception.message,
            "Knowledge answer must not be empty.",
        )


if __name__ == "__main__":
    unittest.main()
