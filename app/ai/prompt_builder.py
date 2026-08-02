"""Prompt builder for AI course generation.

Assembles deterministic text prompts from lesson generation requests.
No LLM calls or external dependencies are used here.
"""

from __future__ import annotations

from app.ai.interfaces import LessonGenerationRequest


class PromptBuilder:
    """Build text prompts for AI lesson generation."""

    def build_lesson_generation_prompt(
        self,
        request: LessonGenerationRequest,
    ) -> str:
        """Build a prompt describing lessons to generate or refine.

        Args:
            request: Lesson candidates to include in the prompt.

        Returns:
            An empty string when there are no lessons, otherwise a
            deterministic multi-lesson prompt.
        """
        if not request.lessons:
            return ""

        lines = [
            "Create a structured training course from the source material below.",
            "",
            "Your task:",
            "1. Infer a concise course title from the material.",
            "2. Transform each source section into a training lesson.",
            "3. For every lesson provide a clear title and a brief description.",
            "",
            "Return ONLY valid JSON.",
            "Do not use Markdown.",
            "Do not wrap JSON in code fences.",
            "Use exactly this schema:",
            "",
            "{",
            '  "course_title": "...",',
            '  "lessons": [',
            "    {",
            '      "title": "...",',
            '      "content": "..."',
            "    }",
            "  ]",
            "}",
            "",
            "Field rules:",
            '- "course_title": short name for the entire course.',
            '- "lessons": one entry per source section, in the same order.',
            '- "title": lesson title.',
            '- "content": brief description of the lesson (2-4 sentences).',
            "",
            "Source material:",
            "",
        ]

        for index, lesson in enumerate(request.lessons, start=1):
            lines.extend(
                [
                    f"Section {index}:",
                    f"Title: {lesson.title}",
                    "",
                    "Content:",
                    lesson.content,
                    "",
                ]
            )

        return "\n".join(lines).rstrip("\n")
