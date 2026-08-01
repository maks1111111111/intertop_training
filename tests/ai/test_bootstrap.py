"""Tests for AI composition root (``app.ai.bootstrap``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.ai.bootstrap import (
    create_course_generation_service,
    create_imported_text_generation_service,
)
from app.ai.config import OpenAIConfig
from app.ai.service import CourseGenerationService
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


if __name__ == "__main__":
    unittest.main()
