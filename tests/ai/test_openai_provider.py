"""Tests for OpenAI AI provider (``app.ai.openai_provider``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.client import DummyAIClient
from app.ai.interfaces import LessonGenerationRequest
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.content.lesson_builder import LessonCandidate


class OpenAICourseGenerationAITests(unittest.TestCase):
    """Tests for :class:`OpenAICourseGenerationAI`."""

    def test_model_is_stored(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertEqual(provider._model, "gpt-4o")

    def test_generate_lessons_raises_not_implemented_error(self) -> None:
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

    def test_injected_client_is_stored(self) -> None:
        injected_client = MagicMock()
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=injected_client,
        )

        self.assertIs(provider._client, injected_client)

    def test_default_client_is_dummy_ai_client(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertIsInstance(provider._client, DummyAIClient)


if __name__ == "__main__":
    unittest.main()
