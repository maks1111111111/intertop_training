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
        '- "structured_practical_task" must model a realistic on-the-job',
        "  work situation.",
        "- Base the task only on information from the source material",
        "  below.",
        "- Do not turn the task into a recap or summary of the lesson",
        "  content.",
        "- Describe concrete actions the employee should perform.",
        '- "structured_practical_task.expected_result" must be verifiable',
        "  and observable.",
        "- If the source material lacks enough detail, create the",
        "  simplest safe task possible from available information; do not",
        "  invent corporate rules or procedures.",
        '- "structured_practical_task.estimated_minutes" should match the',
        "  task scope; typically choose a value between 5 and 30 minutes",
        "  unless the source material clearly supports null.",
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
    ]


def _task_instruction_lines() -> list[str]:
    return [
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
        self.assertIn('"content"', prompt)
        self.assertIn('"learning_objectives"', prompt)
        self.assertIn("5-15 paragraphs", prompt)
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

    def test_prompt_requires_extended_lesson_fields(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First content."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertIn('"structured_practical_task"', prompt)
        self.assertIn('"structured_practical_task.title"', prompt)
        self.assertIn('"structured_practical_task.description"', prompt)
        self.assertIn('"structured_practical_task.expected_result"', prompt)
        self.assertIn('"structured_practical_task.estimated_minutes"', prompt)
        self.assertIn("positive integer estimate", prompt)
        self.assertIn("or null", prompt)
        self.assertIn('"checklist"', prompt)
        self.assertIn('"common_mistakes"', prompt)
        self.assertIn('"key_takeaways"', prompt)
        self.assertIn('"application_tips"', prompt)
        self.assertIn("structured practical", prompt)
        self.assertIn("checklist", prompt)
        self.assertIn("common mistakes", prompt)
        self.assertIn("key takeaways", prompt)
        self.assertIn("tips for applying", prompt)
        self.assertNotIn('"practical_task": "..."', prompt)
        self.assertNotIn(
            '"practical_task": one concrete practical task',
            prompt,
        )
        self.assertIn(
            "Do not invent policies, rules, facts, or procedures",
            prompt,
        )

    def test_prompt_requires_structured_practical_task_quality_rules(self) -> None:
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="First content."),
            ]
        )

        prompt = self.builder.build_lesson_generation_prompt(request)

        self.assertIn("realistic on-the-job", prompt)
        self.assertIn(
            "Base the task only on information from the source material",
            prompt,
        )
        self.assertIn(
            "Do not turn the task into a recap or summary of the lesson",
            prompt,
        )
        self.assertIn(
            "Describe concrete actions the employee should perform",
            prompt,
        )
        self.assertIn("verifiable", prompt)
        self.assertIn("observable", prompt)
        self.assertIn("simplest safe task possible", prompt)
        self.assertIn("invent corporate rules or procedures", prompt)
        self.assertIn("between 5 and 30 minutes", prompt)


if __name__ == "__main__":
    unittest.main()
