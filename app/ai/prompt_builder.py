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
            "1. Infer a concise course title and description from the material.",
            "2. Detect the primary language of the material.",
            "3. Transform each source section into a training lesson.",
            "4. For every lesson provide a title, a brief summary, full",
            "   lesson content, and learning objectives.",
            "",
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
            '      "content": "...",',
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
            '- "content": main educational material for the lesson;',
            "  write 5-15 paragraphs using information from the source",
            "  material; do not use generic filler; do not reduce the",
            "  lesson to a summary; write a complete training lesson.",
            '- "learning_objectives": list of short, measurable outcomes.',
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
