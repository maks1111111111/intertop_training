"""Tests for OpenAI configuration (``app.ai.config``)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.ai.config import OpenAIConfig


class OpenAIConfigTests(unittest.TestCase):
    """Tests for :class:`OpenAIConfig`."""

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-api-key",
            "OPENAI_MODEL": "gpt-4o",
        },
        clear=True,
    )
    def test_from_environment_reads_variables(self) -> None:
        config = OpenAIConfig.from_environment()

        self.assertEqual(config.api_key, "test-api-key")
        self.assertEqual(config.model, "gpt-4o")

    @patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "test-api-key"},
        clear=True,
    )
    def test_from_environment_uses_default_model(self) -> None:
        config = OpenAIConfig.from_environment()

        self.assertEqual(config.api_key, "test-api-key")
        self.assertEqual(config.model, "gpt-4.1-mini")

    @patch.dict(os.environ, {}, clear=True)
    def test_from_environment_raises_when_api_key_missing(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            OpenAIConfig.from_environment()

        self.assertEqual(
            str(context.exception),
            "OPENAI_API_KEY environment variable is not set.",
        )


if __name__ == "__main__":
    unittest.main()
