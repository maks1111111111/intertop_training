"""Tests for AI quiz prompt builder (``app.ai.quiz_prompt_builder``)."""

from __future__ import annotations

import unittest

from app.ai.quiz_interfaces import QuizGenerationRequest
from app.ai.quiz_prompt_builder import QuizPromptBuilder
from app.content.lesson_builder import LessonCandidate


def _json_instruction_lines() -> list[str]:
    return [
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
    ]


def _task_instruction_lines() -> list[str]:
    return [
        "Create a final course quiz from the lesson material below.",
        "",
        "Your task:",
        "1. Write a quiz title and passing score for the course.",
        "2. Create questions that test knowledge from the lessons.",
        "3. Use only information from the provided lesson material.",
        "",
    ]


class QuizPromptBuilderTests(unittest.TestCase):
    """Tests for :class:`QuizPromptBuilder`."""

    def setUp(self) -> None:
        self.builder = QuizPromptBuilder()

    def test_empty_request_returns_empty_string(self) -> None:
        request = QuizGenerationRequest(lessons=())

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(prompt, "")

    def test_single_lesson_prompt(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Safety basics", content="Wear PPE."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    *_task_instruction_lines(),
                    *_json_instruction_lines(),
                    "",
                    "Lesson material:",
                    "",
                    "Lesson 1:",
                    "Slug: lesson_01",
                    "Title: Safety basics",
                    "",
                    "Content:",
                    "Wear PPE.",
                ]
            ),
        )

    def test_multiple_lessons_prompt(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson A", content="Content A."),
                LessonCandidate(title="Lesson B", content="Content B."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    *_task_instruction_lines(),
                    *_json_instruction_lines(),
                    "",
                    "Lesson material:",
                    "",
                    "Lesson 1:",
                    "Slug: lesson_01",
                    "Title: Lesson A",
                    "",
                    "Content:",
                    "Content A.",
                    "",
                    "Lesson 2:",
                    "Slug: lesson_02",
                    "Title: Lesson B",
                    "",
                    "Content:",
                    "Content B.",
                ]
            ),
        )

    def test_json_schema_is_present(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn('"title"', prompt)
        self.assertIn('"passing_score"', prompt)
        self.assertIn('"questions"', prompt)
        self.assertIn('"lesson"', prompt)
        self.assertIn('"question"', prompt)
        self.assertIn('"options"', prompt)
        self.assertIn('"correct"', prompt)

    def test_passing_score_is_present(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn('"passing_score": 80', prompt)
        self.assertIn('"passing_score": integer from 1 to 100', prompt)

    def test_lesson_01_slug_is_present(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn('"lesson": "lesson_01"', prompt)
        self.assertIn("Slug: lesson_01", prompt)

    def test_lesson_content_is_included(self) -> None:
        content = "Detailed lesson material.\nSecond paragraph."
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Custom title", content=content),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("Title: Custom title", prompt)
        self.assertIn(content, prompt)

    def test_prompt_is_deterministic(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content 1."),
                LessonCandidate(title="Lesson 2", content="Content 2."),
            )
        )

        first_prompt = self.builder.build_quiz_generation_prompt(request)
        second_prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(first_prompt, second_prompt)

    def test_order_is_preserved(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Alpha", content="A."),
                LessonCandidate(title="Beta", content="B."),
                LessonCandidate(title="Gamma", content="C."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        alpha_index = prompt.index("Title: Alpha")
        beta_index = prompt.index("Title: Beta")
        gamma_index = prompt.index("Title: Gamma")

        self.assertLess(alpha_index, beta_index)
        self.assertLess(beta_index, gamma_index)
        self.assertIn("Lesson 1:", prompt)
        self.assertIn("Lesson 2:", prompt)
        self.assertIn("Lesson 3:", prompt)
        self.assertIn("Slug: lesson_03", prompt)

    def test_requires_json_only_response(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("Return ONLY valid JSON", prompt)
        self.assertIn("Do not use Markdown", prompt)
        self.assertIn("Do not wrap JSON in code fences", prompt)

    def test_option_rules_are_present(self) -> None:
        request = QuizGenerationRequest(
            lessons=(
                LessonCandidate(title="Lesson 1", content="Content."),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("at least 4 answer options", prompt)
        self.assertIn("exactly one option per question must be true", prompt)


if __name__ == "__main__":
    unittest.main()
