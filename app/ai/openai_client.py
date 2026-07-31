"""OpenAI SDK client implementing :class:`AIClient`."""

from __future__ import annotations

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[misc, assignment]

from app.ai.client import AIClient
from app.ai.config import OpenAIConfig


class OpenAIClient:
    """OpenAI-backed implementation of :class:`AIClient`."""

    def __init__(self, config: OpenAIConfig) -> None:
        if OpenAI is None:
            raise RuntimeError("OpenAI SDK is not installed.")

        self._client = OpenAI(api_key=config.api_key)
        self._model = config.model

    def generate(self, prompt: str) -> str:
        """Send a prompt to OpenAI and return the response text."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        content = response.choices[0].message.content
        if content is None:
            return ""
        return content
