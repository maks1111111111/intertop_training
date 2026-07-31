"""Tests for OpenAI AI provider (``app.ai.openai_provider``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.ai.interfaces import LessonGenerationRequest
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.content.lesson_builder import LessonCandidate


class OpenAICourseGenerationAITests(unittest.TestCase):
    """Tests for :class:`OpenAICourseGenerationAI`."""

    @patch("app.ai.openai_provider.OpenAI")
    def test_model_is_stored(self, mock_openai_class: MagicMock) -> None:
        mock_openai_class.return_value = MagicMock()
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertEqual(provider._model, "gpt-4o")

    @patch("app.ai.openai_provider.OpenAI")
    def test_generate_lessons_raises_not_implemented_error(
        self,
        mock_openai_class: MagicMock,
    ) -> None:
        mock_openai_class.return_value = MagicMock()
        provider = OpenAICourseGenerationAI(model="gpt-4o")
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        with self.assertRaises(NotImplementedError) as context:
            provider.generate_lessons(request)

        self.assertEqual(
            str(context.exception),
            "OpenAI integration is not implemented yet.",
        )

    @patch("app.ai.openai_provider.OpenAI", None)
    def test_raises_runtime_error_when_sdk_missing(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            OpenAICourseGenerationAI(model="gpt-4o")

        self.assertEqual(
            str(context.exception),
            "OpenAI SDK is not installed.",
        )


if __name__ == "__main__":
    unittest.main()
