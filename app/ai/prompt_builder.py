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
            "Generate training lessons.",
            "",
            "Return ONLY valid JSON.",
            "Do not use Markdown.",
            "Do not wrap JSON in code fences.",
            "Use this schema:",
            "",
            "{",
            '  "lessons": [',
            "    {",
            '      "title": "...",',
            '      "content": "..."',
            "    }",
            "  ]",
            "}",
            "",
        ]

        for index, lesson in enumerate(request.lessons, start=1):
            lines.extend(
                [
                    f"Lesson {index}:",
                    f"Title: {lesson.title}",
                    "",
                    "Content:",
                    lesson.content,
                    "",
                ]
            )

        return "\n".join(lines).rstrip("\n")
