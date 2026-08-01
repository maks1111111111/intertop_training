"""Tests for OpenAI AI provider (``app.ai.openai_provider``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.client import DummyAIClient
from app.ai.interfaces import (
    LessonGenerationRequest,
    LessonGenerationResult,
)
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.ai.prompt_builder import PromptBuilder
from app.ai.response_parser import AIResponseParser
from app.content.lesson_builder import LessonCandidate


class OpenAICourseGenerationAITests(unittest.TestCase):
    """Tests for :class:`OpenAICourseGenerationAI`."""

    def test_model_is_stored(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertEqual(provider._model, "gpt-4o")

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

    def test_injected_response_parser_is_stored(self) -> None:
        injected_parser = MagicMock()
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            response_parser=injected_parser,
        )

        self.assertIs(provider._response_parser, injected_parser)

    def test_default_response_parser_is_ai_response_parser(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertIsInstance(
            provider._response_parser,
            AIResponseParser,
        )

    def test_generate_lessons_calls_prompt_builder_once(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            "Generate training lessons."
        )
        mock_parser = MagicMock()
        mock_parser.parse_lessons.return_value = LessonGenerationResult(
            lessons=[],
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

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
        mock_parser = MagicMock()
        mock_parser.parse_lessons.return_value = LessonGenerationResult(
            lessons=[],
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

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
        mock_parser = MagicMock()
        mock_parser.parse_lessons.return_value = LessonGenerationResult(
            lessons=[],
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        provider.generate_lessons(request)

        mock_client.generate.assert_called_once_with(expected_prompt)

    def test_default_prompt_builder_is_prompt_builder(self) -> None:
        provider = OpenAICourseGenerationAI(model="gpt-4o")

        self.assertIsInstance(provider._prompt_builder, PromptBuilder)

    def test_generate_lessons_passes_client_response_to_parser(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            "Generate training lessons."
        )
        mock_parser = MagicMock()
        mock_parser.parse_lessons.return_value = LessonGenerationResult(
            lessons=[],
        )
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        provider.generate_lessons(request)

        mock_parser.parse_lessons.assert_called_once_with("AI response")

    def test_generate_lessons_returns_parser_result_unchanged(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI response"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_lesson_generation_prompt.return_value = (
            "Generate training lessons."
        )
        expected_result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Generated lesson",
                    content="Generated content.",
                )
            ]
        )
        mock_parser = MagicMock()
        mock_parser.parse_lessons.return_value = expected_result
        provider = OpenAICourseGenerationAI(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
        )
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        result = provider.generate_lessons(request)

        self.assertIs(result, expected_result)


if __name__ == "__main__":
    unittest.main()
