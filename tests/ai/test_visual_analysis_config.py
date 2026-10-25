"""Tests for opt-in visual-analysis configuration."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.ai.visual_analysis_config import OpenAIVisualAnalysisConfig


class OpenAIVisualAnalysisConfigTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-api-key",
            "OPENAI_MODEL": "text-model-must-not-be-used",
            "OPENAI_VISUAL_ANALYSIS_MODEL": "vision-model",
        },
        clear=True,
    )
    def test_reads_explicit_visual_model_without_text_model_fallback(self) -> None:
        config = OpenAIVisualAnalysisConfig.from_environment()

        self.assertEqual(config.api_key, "test-api-key")
        self.assertEqual(config.model, "vision-model")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}, clear=True)
    def test_fails_closed_when_visual_model_is_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "OPENAI_VISUAL_ANALYSIS_MODEL"):
            OpenAIVisualAnalysisConfig.from_environment()

    @patch.dict(
        os.environ,
        {"OPENAI_VISUAL_ANALYSIS_MODEL": "vision-model"},
        clear=True,
    )
    def test_requires_api_key(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
            OpenAIVisualAnalysisConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
