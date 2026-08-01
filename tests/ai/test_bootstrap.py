"""Tests for AI composition root (``app.ai.bootstrap``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.ai.bootstrap import create_course_generation_service
from app.ai.config import OpenAIConfig
from app.ai.service import CourseGenerationService


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


if __name__ == "__main__":
    unittest.main()
