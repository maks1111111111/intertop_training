"""Opt-in configuration for the isolated visual-analysis client."""

from __future__ import annotations

import os
from dataclasses import dataclass


_DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class OpenAIVisualAnalysisConfig:
    """Configuration that does not fall back to text-generation settings.

    A visual model must be configured explicitly.  This keeps the future
    visual feature opt-in and avoids accidentally sending source images through
    whichever model currently powers text generation.
    """

    api_key: str
    model: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("visual analysis API key must be configured")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("visual analysis model must be configured")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("visual analysis timeout must be positive")

    @classmethod
    def from_environment(cls) -> "OpenAIVisualAnalysisConfig":
        """Load explicit visual-analysis settings without text-model fallback."""
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key is None or not api_key.strip():
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        model = os.getenv("OPENAI_VISUAL_ANALYSIS_MODEL")
        if model is None or not model.strip():
            raise RuntimeError(
                "OPENAI_VISUAL_ANALYSIS_MODEL environment variable is not set."
            )
        return cls(api_key=api_key, model=model)
