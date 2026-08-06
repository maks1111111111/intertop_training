"""Tests for AI composition root (``app.ai.bootstrap``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.ai.bootstrap import (
    create_course_generation_service,
    create_course_with_quiz_generation_service,
    create_imported_text_generation_service,
    create_practical_task_review_service,
    create_quiz_generation_service,
)
from app.ai.config import OpenAIConfig
from app.ai.openai_review_provider import OpenAIPracticalTaskReviewer
from app.ai.quiz_service import QuizGenerationService
from app.ai.review_service import PracticalTaskReviewService
from app.ai.service import CourseGenerationService
from app.services.course_with_quiz_generation_service import (
    CourseWithQuizGenerationService,
)
from app.services.imported_text_generation_service import (
    ImportedTextGenerationService,
)


class CreateCourseGenerationServiceTests(unittest.TestCase):
    """Tests for :func:`create_course_generation_service`."""

    @patch("app.ai.bootstrap.OpenAICourseGenerationAI.from_config")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_calls_from_environment(
        self,
        mock_from_environment: MagicMock,
        mock_from_config: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_from_environment.return_value = config
        mock_from_config.return_value = MagicMock()

        create_course_generation_service()

        mock_from_environment.assert_called_once_with()

    @patch("app.ai.bootstrap.OpenAICourseGenerationAI.from_config")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_uses_from_config(
        self,
        mock_from_environment: MagicMock,
        mock_from_config: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_from_environment.return_value = config
        mock_from_config.return_value = MagicMock()

        create_course_generation_service()

        mock_from_config.assert_called_once_with(config)

    @patch("app.ai.bootstrap.OpenAICourseGenerationAI.from_config")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_returns_course_generation_service(
        self,
        mock_from_environment: MagicMock,
        mock_from_config: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_from_environment.return_value = config
        mock_provider = MagicMock()
        mock_from_config.return_value = mock_provider

        service = create_course_generation_service()

        self.assertIsInstance(service, CourseGenerationService)

    @patch("app.ai.bootstrap.OpenAICourseGenerationAI.from_config")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_wires_provider_into_service(
        self,
        mock_from_environment: MagicMock,
        mock_from_config: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_from_environment.return_value = config
        mock_provider = MagicMock()
        mock_from_config.return_value = mock_provider

        service = create_course_generation_service()

        self.assertIs(service._provider, mock_provider)


class CreateImportedTextGenerationServiceTests(unittest.TestCase):
    """Tests for :func:`create_imported_text_generation_service`."""

    @patch("app.ai.bootstrap.ImportedTextGenerationService")
    @patch("app.ai.bootstrap.CourseGenerationFlowService")
    @patch("app.ai.bootstrap.CourseGenerationPipelineService")
    @patch("app.ai.bootstrap.create_course_generation_service")
    def test_wires_imported_text_generation_service(
        self,
        mock_create_course_generation_service: MagicMock,
        mock_pipeline_service_class: MagicMock,
        mock_flow_service_class: MagicMock,
        mock_imported_text_service_class: MagicMock,
    ) -> None:
        mock_course_generation_service = MagicMock(spec=CourseGenerationService)
        mock_create_course_generation_service.return_value = (
            mock_course_generation_service
        )
        mock_pipeline_service = MagicMock()
        mock_pipeline_service_class.return_value = mock_pipeline_service
        mock_flow_service = MagicMock()
        mock_flow_service_class.return_value = mock_flow_service
        mock_imported_text_service = MagicMock(spec=ImportedTextGenerationService)
        mock_imported_text_service_class.return_value = mock_imported_text_service

        result = create_imported_text_generation_service()

        mock_create_course_generation_service.assert_called_once_with()
        mock_pipeline_service_class.assert_called_once_with(
            mock_course_generation_service,
        )
        mock_flow_service_class.assert_called_once_with(
            mock_pipeline_service,
        )
        mock_imported_text_service_class.assert_called_once_with(
            flow_service=mock_flow_service,
        )
        self.assertIs(result, mock_imported_text_service)


class CreateQuizGenerationServiceTests(unittest.TestCase):
    """Tests for :func:`create_quiz_generation_service`."""

    @patch("app.ai.bootstrap.QuizGenerationService")
    @patch("app.ai.bootstrap.OpenAIClient")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_wires_quiz_generation_service(
        self,
        mock_from_environment: MagicMock,
        mock_openai_client_class: MagicMock,
        mock_quiz_generation_service_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_from_environment.return_value = config
        mock_client = MagicMock()
        mock_openai_client_class.return_value = mock_client
        mock_quiz_service = MagicMock(spec=QuizGenerationService)
        mock_quiz_generation_service_class.return_value = mock_quiz_service

        result = create_quiz_generation_service()

        mock_from_environment.assert_called_once_with()
        mock_openai_client_class.assert_called_once_with(config)
        mock_quiz_generation_service_class.assert_called_once_with(mock_client)
        self.assertIs(result, mock_quiz_service)


class CreateCourseWithQuizGenerationServiceTests(unittest.TestCase):
    """Tests for :func:`create_course_with_quiz_generation_service`."""

    @patch("app.ai.bootstrap.CourseWithQuizGenerationService")
    @patch("app.ai.bootstrap.QuizGenerationPersistenceService")
    @patch("app.ai.bootstrap.create_quiz_generation_service")
    @patch("app.ai.bootstrap.CourseGenerationPersistenceService")
    def test_wires_course_with_quiz_generation_service(
        self,
        mock_course_persistence_class: MagicMock,
        mock_create_quiz_generation_service: MagicMock,
        mock_quiz_persistence_class: MagicMock,
        mock_course_with_quiz_class: MagicMock,
    ) -> None:
        mock_course_persistence = MagicMock()
        mock_course_persistence_class.return_value = mock_course_persistence
        mock_quiz_generation_service = MagicMock(spec=QuizGenerationService)
        mock_create_quiz_generation_service.return_value = mock_quiz_generation_service
        mock_quiz_persistence = MagicMock()
        mock_quiz_persistence_class.return_value = mock_quiz_persistence
        mock_course_with_quiz_service = MagicMock(
            spec=CourseWithQuizGenerationService,
        )
        mock_course_with_quiz_class.return_value = mock_course_with_quiz_service

        result = create_course_with_quiz_generation_service()

        mock_course_persistence_class.assert_called_once_with()
        mock_create_quiz_generation_service.assert_called_once_with()
        mock_quiz_persistence_class.assert_called_once_with()
        mock_course_with_quiz_class.assert_called_once_with(
            course_persistence_service=mock_course_persistence,
            quiz_generation_service=mock_quiz_generation_service,
            quiz_persistence_service=mock_quiz_persistence,
        )
        self.assertIs(result, mock_course_with_quiz_service)


class CreatePracticalTaskReviewServiceTests(unittest.TestCase):
    """Tests for :func:`create_practical_task_review_service`."""

    @patch("app.ai.bootstrap.PracticalTaskReviewService")
    @patch("app.ai.bootstrap.OpenAIPracticalTaskReviewer.from_config")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_wires_practical_task_review_service(
        self,
        mock_from_environment: MagicMock,
        mock_from_config: MagicMock,
        mock_review_service_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_from_environment.return_value = config
        mock_provider = MagicMock()
        mock_from_config.return_value = mock_provider
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)
        mock_review_service_class.return_value = mock_review_service

        result = create_practical_task_review_service()

        mock_from_environment.assert_called_once_with()
        mock_from_config.assert_called_once_with(config)
        mock_review_service_class.assert_called_once_with(mock_provider)
        self.assertIs(result, mock_review_service)

    @patch("app.ai.bootstrap.PracticalTaskReviewService")
    @patch("app.ai.bootstrap.OpenAIPracticalTaskReviewer.from_config")
    @patch("app.ai.bootstrap.OpenAIConfig.from_environment")
    def test_composition_order(
        self,
        mock_from_environment: MagicMock,
        mock_from_config: MagicMock,
        mock_review_service_class: MagicMock,
    ) -> None:
        call_log: list[str] = []
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_provider = MagicMock(spec=OpenAIPracticalTaskReviewer)
        mock_review_service = MagicMock(spec=PracticalTaskReviewService)

        def record_config() -> OpenAIConfig:
            call_log.append("config")
            return config

        def record_provider(cfg: OpenAIConfig) -> MagicMock:
            call_log.append("provider")
            self.assertIs(cfg, config)
            return mock_provider

        def record_service(provider: MagicMock) -> MagicMock:
            call_log.append("service")
            self.assertIs(provider, mock_provider)
            return mock_review_service

        mock_from_environment.side_effect = record_config
        mock_from_config.side_effect = record_provider
        mock_review_service_class.side_effect = record_service

        result = create_practical_task_review_service()

        self.assertEqual(call_log, ["config", "provider", "service"])
        self.assertIs(result, mock_review_service)


if __name__ == "__main__":
    unittest.main()
