"""OpenAI configuration for the AI integration layer."""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


@dataclass(frozen=True)
class OpenAIConfig:
    """OpenAI API settings loaded from environment variables."""

    api_key: str
    model: str

    @classmethod
    def from_environment(cls) -> OpenAIConfig:
        """Load configuration from ``OPENAI_API_KEY`` and ``OPENAI_MODEL``."""
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set."
            )

        model = os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
        return cls(api_key=api_key, model=model)
