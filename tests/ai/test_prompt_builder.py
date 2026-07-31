"""Tests for AI prompt builder (``app.ai.prompt_builder``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import LessonGenerationRequest
from app.ai.prompt_builder import PromptBuilder
from app.content.lesson_builder import LessonCandidate


class PromptBuilderTests(unittest.TestCase):
    """Tests for :class:`PromptBuilder`."""

    def setUp(self) -> None:
        self.builder = PromptBuilder()

    def test_empty_request_returns_empty_string(self) -> None:
        request = LessonGenerationRequest(lessons=[])

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertEqual(prompt, "")

    def test_single_lesson_prompt(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First content."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    "Generate training lessons.",
                    "",
                    "Lesson 1:",
                    "Title: Section 1",
                    "",
                    "Content:",
                    "First content.",
                ]
            ),
        )

    def test_multiple_lessons_prompt(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First."),
                LessonCandidate(title="Section 2", content="Second."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    "Generate training lessons.",
                    "",
                    "Lesson 1:",
                    "Title: Section 1",
                    "",
                    "Content:",
                    "First.",
                    "",
                    "Lesson 2:",
                    "Title: Section 2",
                    "",
                    "Content:",
                    "Second.",
                ]
            ),
        )

    def test_order_is_preserved(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Alpha", content="A."),
                LessonCandidate(title="Beta", content="B."),
                LessonCandidate(title="Gamma", content="C."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        alpha_index = prompt.index("Title: Alpha")
        beta_index = prompt.index("Title: Beta")
        gamma_index = prompt.index("Title: Gamma")

        self.assertLess(alpha_index, beta_index)
        self.assertLess(beta_index, gamma_index)
        self.assertIn("Lesson 1:", prompt)
        self.assertIn("Lesson 2:", prompt)
        self.assertIn("Lesson 3:", prompt)

    def test_title_and_content_are_included_unchanged(self) -> None:
        title = "  Custom Title  "
        content = "Line one.\nLine two."
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title=title, content=content),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertIn(f"Title: {title}", prompt)
        self.assertIn(content, prompt)


if __name__ == "__main__":
    unittest.main()
