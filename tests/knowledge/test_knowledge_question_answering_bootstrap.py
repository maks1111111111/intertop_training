"""Tests for Knowledge Base question answering bootstrap."""

from __future__ import annotations

import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from app.ai.client import AIClient
from app.ai.config import OpenAIConfig
from app.ai.knowledge_answer_service import KnowledgeAnswerService
from app.knowledge.context_service import KnowledgeRetrievalContextService
from app.knowledge.question_answering_bootstrap import (
    create_knowledge_question_answering_service,
)
from app.knowledge.question_answering_service import KnowledgeQuestionAnsweringService


class _RecordingClient(AIClient):
    """Minimal AI client stub for bootstrap wiring tests."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "{}"


class CreateKnowledgeQuestionAnsweringServiceTests(unittest.TestCase):
    """Tests for :func:`create_knowledge_question_answering_service`."""

    def test_returns_knowledge_question_answering_service(self) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        client = _RecordingClient()

        service = create_knowledge_question_answering_service(
            config,
            client=client,
        )

        self.assertIsInstance(service, KnowledgeQuestionAnsweringService)

    def test_composes_default_context_service(self) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        client = _RecordingClient()

        service = create_knowledge_question_answering_service(
            config,
            client=client,
        )

        self.assertIsInstance(
            service._context_service,
            KnowledgeRetrievalContextService,
        )

    @patch(
        "app.knowledge.question_answering_bootstrap."
        "create_knowledge_answer_service_from_config"
    )
    def test_composes_knowledge_answer_service(
        self,
        mock_create_answer_service: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        answer_service = MagicMock(spec=KnowledgeAnswerService)
        mock_create_answer_service.return_value = answer_service

        service = create_knowledge_question_answering_service(config)

        mock_create_answer_service.assert_called_once_with(
            config,
            client=None,
            prompt_builder=None,
            response_parser=None,
            validator=None,
        )
        self.assertIs(service._answer_service, answer_service)

    @patch(
        "app.knowledge.question_answering_bootstrap."
        "create_knowledge_answer_service_from_config"
    )
    def test_injected_client_is_passed_to_answer_service_factory(
        self,
        mock_create_answer_service: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        client = _RecordingClient()
        answer_service = MagicMock(spec=KnowledgeAnswerService)
        mock_create_answer_service.return_value = answer_service

        create_knowledge_question_answering_service(
            config,
            client=client,
        )

        mock_create_answer_service.assert_called_once_with(
            config,
            client=client,
            prompt_builder=None,
            response_parser=None,
            validator=None,
        )

    def test_injected_context_service_is_used(self) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        client = _RecordingClient()
        context_service = KnowledgeRetrievalContextService()
        answer_service = KnowledgeAnswerService(provider=client)

        service = create_knowledge_question_answering_service(
            config,
            client=client,
            context_service=context_service,
            answer_service=answer_service,
        )

        self.assertIs(service._context_service, context_service)
        self.assertIs(service._answer_service, answer_service)

    @patch(
        "app.knowledge.question_answering_bootstrap."
        "create_knowledge_answer_service_from_config"
    )
    def test_injected_answer_service_skips_factory(
        self,
        mock_create_answer_service: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        client = _RecordingClient()
        answer_service = KnowledgeAnswerService(provider=client)

        service = create_knowledge_question_answering_service(
            config,
            answer_service=answer_service,
        )

        mock_create_answer_service.assert_not_called()
        self.assertIs(service._answer_service, answer_service)

    @patch(
        "app.knowledge.question_answering_bootstrap."
        "create_knowledge_answer_service_from_config"
    )
    def test_no_duplicate_answer_pipeline_created(
        self,
        mock_create_answer_service: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        answer_service = MagicMock(spec=KnowledgeAnswerService)
        mock_create_answer_service.return_value = answer_service

        create_knowledge_question_answering_service(config)

        mock_create_answer_service.assert_called_once()

    @patch(
        "app.knowledge.question_answering_bootstrap."
        "create_knowledge_answer_service_from_config"
    )
    def test_forwards_prompt_builder_response_parser_validator(
        self,
        mock_create_answer_service: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        prompt_builder = MagicMock()
        response_parser = MagicMock()
        validator = MagicMock()
        mock_create_answer_service.return_value = MagicMock(
            spec=KnowledgeAnswerService
        )

        create_knowledge_question_answering_service(
            config,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            validator=validator,
        )

        mock_create_answer_service.assert_called_once_with(
            config,
            client=None,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            validator=validator,
        )


if __name__ == "__main__":
    unittest.main()
