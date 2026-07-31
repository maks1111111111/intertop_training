"""Tests for OpenAI AI provider (``app.ai.openai_provider``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.client import DummyAIClient
from app.ai.interfaces import LessonGenerationRequest
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.ai.prompt_builder import PromptBuilder
from app.content.lesson_builder import LessonCandidate


class OpenAICourseGenerationAITests(unittest.TestCase):
    """Tests for :class:`OpenAICourseGenerationAI`."""

    def test_model_is_stored(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertEqual(provider._model, "gpt-4o")

    def test_generate_lessons_raises_not_implemented_error(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            "Generate training lessons."
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        with self.assertRaises(NotImplementedError) as context:
            provider.generate_lessons(request)

        self.assertEqual(
            str(context.exception),
            "Lesson parsing is not implemented yet.",
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

    def test_generate_lessons_calls_prompt_builder_once(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            "Generate training lessons."
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        with self.assertRaises(NotImplementedError):
            provider.generate_lessons(request)

        mock_prompt_builder.build_lesson_generation_prompt.assert_called_once_with(
            request
        )

    def test_generate_lessons_calls_client_generate_once(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            "Generate training lessons."
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        with self.assertRaises(NotImplementedError):
            provider.generate_lessons(request)

        mock_client.generate.assert_called_once_with("Generate training lessons.")

    def test_generate_lessons_passes_prompt_builder_output_to_client(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        expected_prompt = (
            "Generate training lessons.\n\n"
            "Lesson 1:\n"
            "Title: Section 1\n\n"
            "Content:\n"
            "Content."
        )
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            expected_prompt
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        with self.assertRaises(NotImplementedError):
            provider.generate_lessons(request)

        mock_client.generate.assert_called_once_with(expected_prompt)

    def test_default_prompt_builder_is_prompt_builder(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertIsInstance(provider._prompt_builder, PromptBuilder)


if __name__ == "__main__":
    unittest.main()
