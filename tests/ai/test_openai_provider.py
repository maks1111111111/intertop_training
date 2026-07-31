"""Tests for OpenAI AI provider (``app.ai.openai_provider``)."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
