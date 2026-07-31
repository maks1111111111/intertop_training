"""Low-level AI client abstraction.

Defines the protocol used by AI providers to send prompts and receive
text responses. No network calls or SDK integration are included here.
"""

from __future__ import annotations

from typing import Protocol


class AIClient(Protocol):
    """Protocol for backends that execute a single prompt and return text."""

    def generate(self, prompt: str) -> str:
        """Send a prompt to the AI backend and return the response text."""
        ...


class DummyAIClient:
    """Placeholder AI client for tests and future provider wiring."""

    def generate(self, prompt: str) -> str:
        """Generate text from a prompt."""
        raise NotImplementedError(
            "AI client generation is not implemented yet."
        )
