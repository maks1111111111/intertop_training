"""Tests for AI quiz prompt builder (``app.ai.quiz_prompt_builder``)."""

from __future__ import annotations

import unittest

from app.ai.quiz_coverage import (
    create_quiz_generation_request,
    lesson_slug_for_index,
    resolve_lesson_question_targets,
    total_question_target,
)
from app.ai.quiz_interfaces import QuizGenerationRequest
from app.ai.quiz_prompt_builder import QuizPromptBuilder
from app.content.lesson_builder import LessonCandidate


def _coverage_instruction_lines(request: QuizGenerationRequest) -> list[str]:
    targets = resolve_lesson_question_targets(request)
    required_total = total_question_target(request)
    lines = [
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
    return lines


def _json_instruction_lines(required_total: int) -> list[str]:
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
    ]


def _task_instruction_lines() -> list[str]:
    return [
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
    ]


def _quality_instruction_lines() -> list[str]:
    return [
        "Question quality:",
        "- Cover facts and rules from the source material.",
        "- Test understanding, not only memorization.",
        "- Include application in a realistic work situation.",
        "- Include recognizing a mistake or choosing the best action.",
        "- Do not create near-duplicate questions for the same lesson.",
        "- Vary which option is marked correct; do not always use the first option.",
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
        request = create_quiz_generation_request(
            (LessonCandidate(title="Safety basics", content="Wear PPE."),)
        )
        required_total = total_question_target(request)

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    *_task_instruction_lines(),
                    *_coverage_instruction_lines(request),
                    "",
                    *_quality_instruction_lines(),
                    "",
                    *_json_instruction_lines(required_total),
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
        request = create_quiz_generation_request(
            (
                LessonCandidate(title="Lesson A", content="Content A."),
                LessonCandidate(title="Lesson B", content="Content B."),
            )
        )
        required_total = total_question_target(request)

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    *_task_instruction_lines(),
                    *_coverage_instruction_lines(request),
                    "",
                    *_quality_instruction_lines(),
                    "",
                    *_json_instruction_lines(required_total),
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
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
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
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn('"passing_score": 80', prompt)
        self.assertIn('"passing_score": integer from 1 to 100', prompt)

    def test_lesson_01_slug_is_present(self) -> None:
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn('"lesson": "lesson_01"', prompt)
        self.assertIn("Slug: lesson_01", prompt)

    def test_lesson_content_is_included(self) -> None:
        content = "Detailed lesson material.\nSecond paragraph."
        request = create_quiz_generation_request(
            (LessonCandidate(title="Custom title", content=content),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("Title: Custom title", prompt)
        self.assertIn(content, prompt)

    def test_prompt_is_deterministic(self) -> None:
        request = create_quiz_generation_request(
            (
                LessonCandidate(title="Lesson 1", content="Content 1."),
                LessonCandidate(title="Lesson 2", content="Content 2."),
            )
        )

        first_prompt = self.builder.build_quiz_generation_prompt(request)
        second_prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertEqual(first_prompt, second_prompt)

    def test_order_is_preserved(self) -> None:
        request = create_quiz_generation_request(
            (
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
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("Return ONLY valid JSON", prompt)
        self.assertIn("Do not use Markdown", prompt)
        self.assertIn("Do not wrap JSON in code fences", prompt)

    def test_option_rules_are_present(self) -> None:
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("at least 4 answer options", prompt)
        self.assertIn("exactly one option per question must be true", prompt)

    def test_prompt_contains_total_target(self) -> None:
        request = create_quiz_generation_request(
            (
                LessonCandidate(title="Short", content="Brief."),
                LessonCandidate(title="Long", content="x" * 2500),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn(
            f"- Total questions required: {total_question_target(request)}.",
            prompt,
        )

    def test_prompt_contains_per_lesson_required_counts(self) -> None:
        request = create_quiz_generation_request(
            (
                LessonCandidate(title="Short", content="Brief."),
                LessonCandidate(title="Medium", content="x" * 900),
            )
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("- lesson_01: 2 questions", prompt)
        self.assertIn("- lesson_02: 3 questions", prompt)

    def test_prompt_requires_each_lesson_coverage(self) -> None:
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("- Do not skip any lesson.", prompt)
        self.assertIn("- Do not create fewer questions than required.", prompt)

    def test_prompt_requires_question_variety(self) -> None:
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("Cover facts and rules from the source material.", prompt)
        self.assertIn("Include application in a realistic work situation.", prompt)
        self.assertIn(
            "Include recognizing a mistake or choosing the best action.",
            prompt,
        )

    def test_prompt_requires_varied_correct_option_position(self) -> None:
        request = create_quiz_generation_request(
            (LessonCandidate(title="Lesson 1", content="Content."),)
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn(
            "Vary which option is marked correct; do not always use the first option.",
            prompt,
        )

    def test_ru_output_language_requires_russian_quiz_content(self) -> None:
        request = create_quiz_generation_request(
            (LessonCandidate(title="Safety", content="English lesson content."),),
            output_language="ru",
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn("Output language (mandatory):", prompt)
        self.assertIn('Language code: "ru"', prompt)
        self.assertIn("only in Russian", prompt)
        self.assertIn("quiz title", prompt)
        self.assertIn("question text", prompt)

    def test_quiz_uses_course_output_language_from_request(self) -> None:
        request = QuizGenerationRequest(
            lessons=(LessonCandidate(title="Lesson", content="Content."),),
            questions_per_lesson=2,
            lesson_question_targets=(2,),
            output_language="kk",
        )

        prompt = self.builder.build_quiz_generation_prompt(request)

        self.assertIn('Language code: "kk"', prompt)
        self.assertIn("only in Kazakh", prompt)


if __name__ == "__main__":
    unittest.main()
