"""Parse AI model responses into structured lesson generation results."""

from __future__ import annotations

from app.ai.interfaces import LessonGenerationResult


class AIResponseParser:
    """Convert raw AI text responses into :class:`LessonGenerationResult`."""

    def parse_lessons(self, response: str) -> LessonGenerationResult:
        """Parse model output into lesson generation results.

        An empty response returns an empty result. Non-empty responses are
        not parsed yet.
        """
        if response == "":
            return LessonGenerationResult(lessons=[])

        raise NotImplementedError(
            "AI response parsing is not implemented yet."
        )
