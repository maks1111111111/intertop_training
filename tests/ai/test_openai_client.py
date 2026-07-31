"""Tests for OpenAI client (``app.ai.openai_client``)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.ai.config import OpenAIConfig
from app.ai.openai_client import OpenAIClient


class OpenAIClientTests(unittest.TestCase):
    """Tests for :class:`OpenAIClient`."""

    def setUp(self) -> None:
        self.config = OpenAIConfig(
            api_key="test-api-key",
            model="gpt-4.1-mini",
        )

    @patch("app.ai.openai_client.OpenAI")
    def test_model_is_stored(self, mock_openai_class: MagicMock) -> None:
        client = OpenAIClient(self.config)

        self.assertEqual(client._model, "gpt-4.1-mini")

    @patch("app.ai.openai_client.OpenAI")
    def test_api_key_is_passed_to_openai(
        self,
        mock_openai_class: MagicMock,
    ) -> None:
        OpenAIClient(self.config)

        mock_openai_class.assert_called_once_with(api_key="test-api-key")

    @patch("app.ai.openai_client.OpenAI")
    def test_generate_calls_chat_completions_create(
        self,
        mock_openai_class: MagicMock,
    ) -> None:
        mock_sdk_client = MagicMock()
        mock_openai_class.return_value = mock_sdk_client
        mock_message = MagicMock()
        mock_message.content = "Generated response."
        mock_sdk_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=mock_message)],
        )

        client = OpenAIClient(self.config)
        result = client.generate("Generate training lessons.")

        mock_sdk_client.chat.completions.create.assert_called_once_with(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": "Generate training lessons.",
                }
            ],
        )
        self.assertEqual(result, "Generated response.")

    @patch("app.ai.openai_client.OpenAI")
    def test_generate_passes_prompt_unchanged(
        self,
        mock_openai_class: MagicMock,
    ) -> None:
        mock_sdk_client = MagicMock()
        mock_openai_class.return_value = mock_sdk_client
        mock_message = MagicMock()
        mock_message.content = "OK"
        mock_sdk_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=mock_message)],
        )

        prompt = "Lesson 1:\nTitle: Section 1\n\nContent:\nBody text."
        client = OpenAIClient(self.config)

        client.generate(prompt)

        call_kwargs = mock_sdk_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["messages"][0]["content"], prompt)

    @patch("app.ai.openai_client.OpenAI")
    def test_generate_returns_content(
        self,
        mock_openai_class: MagicMock,
    ) -> None:
        mock_sdk_client = MagicMock()
        mock_openai_class.return_value = mock_sdk_client
        mock_message = MagicMock()
        mock_message.content = "Structured lesson output."
        mock_sdk_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=mock_message)],
        )

        client = OpenAIClient(self.config)

        self.assertEqual(
            client.generate("Prompt."),
            "Structured lesson output.",
        )

    @patch("app.ai.openai_client.OpenAI")
    def test_generate_returns_empty_string_when_content_is_none(
        self,
        mock_openai_class: MagicMock,
    ) -> None:
        mock_sdk_client = MagicMock()
        mock_openai_class.return_value = mock_sdk_client
        mock_message = MagicMock()
        mock_message.content = None
        mock_sdk_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=mock_message)],
        )

        client = OpenAIClient(self.config)

        self.assertEqual(client.generate("Prompt."), "")

    @patch("app.ai.openai_client.OpenAI", None)
    def test_raises_runtime_error_when_sdk_missing(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            OpenAIClient(self.config)

        self.assertEqual(
            str(context.exception),
            "OpenAI SDK is not installed.",
        )


if __name__ == "__main__":
    unittest.main()
