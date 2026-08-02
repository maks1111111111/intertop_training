"""Prompt builder for AI quiz generation.

Assembles deterministic text prompts from quiz generation requests.
No LLM calls or external dependencies are used here.
"""

from __future__ import annotations

from app.ai.quiz_interfaces import QuizGenerationRequest


class QuizPromptBuilder:
    """Build text prompts for AI quiz generation."""

    def build_quiz_generation_prompt(
        self,
        request: QuizGenerationRequest,
    ) -> str:
        """Build a prompt describing a course quiz to generate.

        Args:
            request: Lesson candidates to include in the prompt.

        Returns:
            An empty string when there are no lessons, otherwise a
            deterministic multi-lesson quiz prompt.
        """
        if not request.lessons:
            return ""

        lines = [
            "Create a final course quiz from the lesson material below.",
            "",
            "Your task:",
            "1. Write a quiz title and passing score for the course.",
            "2. Create questions that test knowledge from the lessons.",
            "3. Use only information from the provided lesson material.",
            "",
            "Return ONLY valid JSON.",
            "Do not use Markdown.",
            "Do not wrap JSON in code fences.",
            "Use exactly this schema:",
            "",
            "{",
            '  "title": "...",',
            '  "passing_score": 80,',
            '  "questions": [',
            "    {",
            '      "id": "...",',
            '      "lesson": "lesson_01",',
            '      "question": "...",',
            '      "options": [',
            "        {",
            '          "id": "...",',
            '          "text": "...",',
            '          "correct": true',
            "        }",
            "      ]",
            "    }",
            "  ]",
            "}",
            "",
            "Field rules:",
            '- "title": name of the final course quiz.',
            '- "passing_score": integer from 1 to 100 (use 80 if unsure).',
            '- "questions": one or more questions linked to lessons.',
            '- "id": unique question identifier.',
            '- "lesson": lesson slug (lesson_01, lesson_02, etc.).',
            '- "question": clear question text based on lesson content.',
            '- "options": at least 4 answer options per question.',
            '- "correct": exactly one option per question must be true.',
            "  All other options must be false.",
            "",
            "Lesson material:",
            "",
        ]

        for index, lesson in enumerate(request.lessons, start=1):
            lesson_slug = f"lesson_{index:02d}"
            lines.extend(
                [
                    f"Lesson {index}:",
                    f"Slug: {lesson_slug}",
                    f"Title: {lesson.title}",
                    "",
                    "Content:",
                    lesson.content,
                    "",
                ]
            )

        return "\n".join(lines).rstrip("\n")
