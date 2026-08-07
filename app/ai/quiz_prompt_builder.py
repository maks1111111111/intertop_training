"""Prompt builder for AI quiz generation.

Assembles deterministic text prompts from quiz generation requests.
No LLM calls or external dependencies are used here.
"""

from __future__ import annotations

from app.ai.quiz_coverage import (
    lesson_slug_for_index,
    resolve_lesson_question_targets,
    total_question_target,
)
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

        targets = resolve_lesson_question_targets(request)
        required_total = total_question_target(request)

        lines = [
            "Create a final course quiz from the lesson material below.",
            "",
            "Your task:",
            "1. Write a quiz title and passing score for the course.",
            (
                "2. Create exactly the required number of questions for each "
                "lesson listed below."
            ),
            "3. Use only information from the provided lesson material.",
            "4. Do not invent policies, facts, or procedures absent from the source.",
            "",
            "Coverage requirements:",
            f"- Total questions required: {required_total}.",
            "- Do not create fewer questions than required.",
            "- Do not skip any lesson.",
            "- Each question must use the lesson slug shown for that lesson.",
            "- Question identifiers must be unique across the whole quiz.",
            "",
            "Required questions per lesson:",
        ]

        for lesson_index, required_count in enumerate(targets, start=1):
            lesson_slug = lesson_slug_for_index(lesson_index)
            lines.append(f"- {lesson_slug}: {required_count} questions")

        lines.extend(
            [
                "",
                "Question quality:",
                "- Cover facts and rules from the source material.",
                "- Test understanding, not only memorization.",
                "- Include application in a realistic work situation.",
                "- Include recognizing a mistake or choosing the best action.",
                "- Do not create near-duplicate questions for the same lesson.",
                "- Vary which option is marked correct; do not always use the first option.",
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
                (
                    f'- "questions": exactly {required_total} questions in total, '
                    "matching the per-lesson counts above."
                ),
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
        )

        for index, lesson in enumerate(request.lessons, start=1):
            lesson_slug = lesson_slug_for_index(index)
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
