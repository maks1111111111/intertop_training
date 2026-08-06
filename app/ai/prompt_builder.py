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
            "   lesson content, learning objectives, a structured practical",
            "   task with title, instructions, expected result, and estimated",
            "   completion time, a checklist, common mistakes, key takeaways,",
            "   and application tips.",
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
            "      ],",
            '      "structured_practical_task": {',
            '        "title": "...",',
            '        "description": "...",',
            '        "expected_result": "...",',
            '        "estimated_minutes": 10',
            "      },",
            '      "checklist": [',
            '        "...",',
            '        "..."',
            "      ],",
            '      "common_mistakes": [',
            '        "...",',
            '        "..."',
            "      ],",
            '      "key_takeaways": [',
            '        "...",',
            '        "..."',
            "      ],",
            '      "application_tips": [',
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
            '- "structured_practical_task": one concrete hands-on exercise or',
            "  work scenario based on the source material; JSON object.",
            '- "structured_practical_task.title": short, action-oriented',
            "  task title.",
            '- "structured_practical_task.description": clear instructions',
            "  describing what the learner should do.",
            '- "structured_practical_task.expected_result": observable result',
            "  that indicates successful completion.",
            '- "structured_practical_task.estimated_minutes": realistic',
            "  positive integer estimate for completing the task, or null",
            "  when the source material does not support a reasonable",
            "  estimate.",
            '- "checklist": list of short, actionable verification steps.',
            '- "common_mistakes": list of typical mistakes relevant to the',
            "  source material.",
            '- "key_takeaways": list of main points the learner should',
            "  remember.",
            '- "application_tips": list of concrete tips for applying the',
            "  knowledge at work.",
            "- Do not invent policies, rules, facts, or procedures that are",
            "  not supported by the source material.",
            "- If the source material is insufficient for a specific item,",
            "  create a cautious item based only on available information",
            "  without invented requirements.",
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
