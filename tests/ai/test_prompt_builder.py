"""Tests for AI prompt builder (``app.ai.prompt_builder``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import LessonGenerationRequest
from app.ai.prompt_builder import PromptBuilder
from app.content.lesson_builder import LessonCandidate


def _json_instruction_lines() -> list[str]:
    return [
        "Return ONLY valid JSON.",
        "Do not use Markdown.",
        "Do not wrap JSON in code fences.",
        "Use exactly this schema:",
        "",
        "{",
        '  "course": {',
        '    "title": "...",',
        '    "description": "...",',
        '    "language": "..."',
        "  },",
        '  "lessons": [',
        "    {",
        '      "title": "...",',
        '      "summary": "...",',
        '      "learning_objectives": [',
        '        "...",',
        '        "..."',
        "      ]",
        "    }",
        "  ]",
        "}",
        "",
        "Field rules:",
        '- "course.title": short name for the entire course.',
        '- "course.description": brief overview of the course (2-4 sentences).',
        '- "course.language": ISO 639-1 language code (e.g. "ru", "en").',
        "  This field is required.",
        '- "lessons": one entry per source section, in the same order.',
        '- "title": lesson title.',
        '- "summary": brief description of the lesson (2-4 sentences).',
        '- "learning_objectives": list of short, measurable outcomes.',
    ]


def _task_instruction_lines() -> list[str]:
    return [
        "Create a structured training course from the source material below.",
        "",
        "Your task:",
        "1. Infer a concise course title and description from the material.",
        "2. Detect the primary language of the material.",
        "3. Transform each source section into a training lesson.",
        "4. For every lesson provide a title, a brief summary, and",
        "   learning objectives.",
        "",
    ]


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
                    *_task_instruction_lines(),
                    *_json_instruction_lines(),
                    "",
                    "Source material:",
                    "",
                    "Section 1:",
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
                    *_task_instruction_lines(),
                    *_json_instruction_lines(),
                    "",
                    "Source material:",
                    "",
                    "Section 1:",
                    "Title: Section 1",
                    "",
                    "Content:",
                    "First.",
                    "",
                    "Section 2:",
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
        self.assertIn("Section 1:", prompt)
        self.assertIn("Section 2:", prompt)
        self.assertIn("Section 3:", prompt)

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

    def test_prompt_requires_structured_json_response(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First content."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertIn("Return ONLY valid JSON", prompt)
        self.assertIn('"course"', prompt)
        self.assertIn('"language"', prompt)
        self.assertIn('"lessons"', prompt)
        self.assertIn('"title"', prompt)
        self.assertIn('"summary"', prompt)
        self.assertIn('"learning_objectives"', prompt)
        self.assertIn("This field is required.", prompt)

    def test_prompt_describes_course_and_lesson_fields(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First content."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertIn("Detect the primary language", prompt)
        self.assertIn("Source material:", prompt)
        self.assertIn(
            '"course.language": ISO 639-1 language code (e.g. "ru", "en").',
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
