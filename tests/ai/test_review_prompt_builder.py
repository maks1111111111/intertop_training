"""Tests for AI review prompt builder (``app.ai.review_prompt_builder``)."""

from __future__ import annotations

import unittest

from app.ai.review_interfaces import ReviewCriterion, ReviewRequest
from app.ai.review_prompt_builder import ReviewPromptBuilder


def _sample_criterion(
    criterion_id: str = "completeness",
    title: str = "Completeness",
    description: str = "Covers all required steps.",
    max_score: int = 5,
) -> ReviewCriterion:
    return ReviewCriterion(
        id=criterion_id,
        title=title,
        description=description,
        max_score=max_score,
    )


def _json_schema_lines() -> list[str]:
    return [
        "Return ONLY valid JSON.",
        "Do not use Markdown.",
        "Do not wrap JSON in code fences.",
        "Use exactly this schema:",
        "",
        "{",
        '  "score": 0,',
        '  "max_score": 0,',
        '  "passed": false,',
        '  "feedback": {',
        '    "summary": "...",',
        '    "strengths": [',
        '      "..."',
        '    ],',
        '    "improvements": [',
        '      "..."',
        '    ]',
        "  }",
        "}",
    ]


def _language_instruction_lines(language: str) -> list[str]:
    labels = {
        "ru": "Russian",
        "kk": "Kazakh",
        "en": "English",
    }
    label = labels.get(language, language)
    lines = [
        "",
        "Response language:",
        f"- Language code: {language}",
        f"- Write all feedback strings in {label}.",
        (
            "- feedback.summary, every feedback.strengths item, and every "
            "feedback.improvements item must use the same response language."
        ),
        "- Do not mix languages within the feedback.",
    ]
    if language != "en":
        lines.append(
            "- Do not reply in English unless the response language code is en."
        )
    return lines


def _scoring_rule_lines(max_score_rule: str) -> list[str]:
    return [
        "",
        "Scoring rules:",
        "- score must be an integer from 0 to max_score.",
        max_score_rule,
        (
            "- passed must be true when score is at least 80% of max_score; "
            "otherwise false."
        ),
        "- feedback.summary must briefly explain the overall evaluation.",
        (
            "- feedback.strengths must list specific elements the learner "
            "did well."
        ),
        "- feedback.improvements must list concrete gaps or next steps.",
        (
            "- Feedback must be specific, actionable, respectful, and based "
            "on the answer."
        ),
        (
            "- All feedback strings must be written in the response language "
            "specified above."
        ),
        "- Do not invent requirements or reward unrelated information.",
    ]


def _role_lines(language: str = "ru") -> list[str]:
    return [
        "You are an objective reviewer of a learner's practical-task answer.",
        "Evaluate only against the supplied task, expected result, and criteria.",
        "Do not invent requirements, policies, facts, or missing source information.",
        "Do not reward information unrelated to the task.",
        *_language_instruction_lines(language),
    ]


class ReviewPromptBuilderTests(unittest.TestCase):
    """Tests for :class:`ReviewPromptBuilder`."""

    def setUp(self) -> None:
        self.builder = ReviewPromptBuilder()

    def test_single_criterion_prompt(self) -> None:
        request = ReviewRequest(
            lesson_title="Safety Basics",
            practical_task_title="Inspect the work area",
            practical_task_description="Walk through the area and identify hazards.",
            expected_result="All hazards are documented and addressed.",
            learner_answer="I checked the floor and removed loose cables.",
            criteria=(_sample_criterion(),),
        )

        prompt = self.builder.build(request)

        self.assertIn("Lesson context:", prompt)
        self.assertIn("Safety Basics", prompt)
        self.assertIn("Title: Inspect the work area", prompt)
        self.assertIn("Walk through the area and identify hazards.", prompt)
        self.assertIn("All hazards are documented and addressed.", prompt)
        self.assertIn("I checked the floor and removed loose cables.", prompt)
        self.assertIn("Criterion 1:", prompt)
        self.assertIn("ID: completeness", prompt)
        self.assertIn("Title: Completeness", prompt)
        self.assertIn("Description: Covers all required steps.", prompt)
        self.assertIn("Maximum score: 5", prompt)
        self.assertIn("The maximum score is the sum of criterion scores: 5.", prompt)
        for line in _json_schema_lines():
            self.assertIn(line, prompt)
        self.assertIn(
            "- max_score must be 5 (sum of all criterion maximum scores).",
            prompt,
        )

    def test_exact_prompt_single_criterion(self) -> None:
        request = ReviewRequest(
            lesson_title="Safety Basics",
            practical_task_title="Inspect the work area",
            practical_task_description="Walk through the area.",
            expected_result="Hazards addressed.",
            learner_answer="I removed cables.",
            criteria=(_sample_criterion(),),
        )

        prompt = self.builder.build(request)

        self.assertEqual(
            prompt,
            "\n".join(
                [
                    *_role_lines(),
                    "",
                    "Lesson context:",
                    "Safety Basics",
                    "",
                    "Practical task:",
                    "Title: Inspect the work area",
                    "",
                    "Instructions:",
                    "Walk through the area.",
                    "",
                    "Expected result:",
                    "Hazards addressed.",
                    "",
                    "Evaluation criteria:",
                    "",
                    "Criterion 1:",
                    "ID: completeness",
                    "Title: Completeness",
                    "Description: Covers all required steps.",
                    "Maximum score: 5",
                    "",
                    "The maximum score is the sum of criterion scores: 5.",
                    "",
                    "Learner answer:",
                    "I removed cables.",
                    "",
                    *_json_schema_lines(),
                    *_scoring_rule_lines(
                        "- max_score must be 5 (sum of all criterion maximum scores)."
                    ),
                ]
            ),
        )

    def test_multiple_criteria_preserves_order(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson 1",
            practical_task_title="Task",
            practical_task_description="Do the task.",
            expected_result="Task completed.",
            learner_answer="Done.",
            criteria=(
                _sample_criterion("completeness", "Completeness", "Covers steps.", 5),
                _sample_criterion("accuracy", "Accuracy", "Uses correct facts.", 3),
            ),
        )

        prompt = self.builder.build(request)

        completeness_index = prompt.index("Criterion 1:")
        accuracy_index = prompt.index("Criterion 2:")
        self.assertLess(completeness_index, accuracy_index)
        self.assertIn("ID: completeness", prompt)
        self.assertIn("ID: accuracy", prompt)
        self.assertIn("Maximum score: 3", prompt)
        self.assertIn("The maximum score is the sum of criterion scores: 8.", prompt)
        self.assertIn(
            "- max_score must be 8 (sum of all criterion maximum scores).",
            prompt,
        )

    def test_empty_criteria_prompt(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson 1",
            practical_task_title="Task",
            practical_task_description="Do the task.",
            expected_result="Task completed.",
            learner_answer="Done.",
            criteria=(),
        )

        prompt = self.builder.build(request)

        self.assertIn("No additional criteria were provided.", prompt)
        self.assertIn(
            "Evaluate the answer only against the practical task and expected result",
            prompt,
        )
        self.assertIn("The maximum score for this review is 100.", prompt)
        self.assertIn("- max_score must be 100.", prompt)
        self.assertNotIn("Criterion 1:", prompt)

    def test_values_preserved_without_normalization(self) -> None:
        request = ReviewRequest(
            lesson_title="  Lesson title  ",
            practical_task_title="  Task title  ",
            practical_task_description="Line one.\nLine two.",
            expected_result="  Expected  ",
            learner_answer="  Answer line.\nSecond line.  ",
            criteria=(),
        )

        prompt = self.builder.build(request)

        self.assertIn("  Lesson title  ", prompt)
        self.assertIn("Title:   Task title  ", prompt)
        self.assertIn("Line one.\nLine two.", prompt)
        self.assertIn("  Expected  ", prompt)
        self.assertIn("  Answer line.\nSecond line.  ", prompt)

    def test_prompt_requires_json_only_and_no_markdown(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson",
            practical_task_title="Task",
            practical_task_description="Description.",
            expected_result="Result.",
            learner_answer="Answer.",
            criteria=(),
        )

        prompt = self.builder.build(request)

        self.assertIn("Return ONLY valid JSON.", prompt)
        self.assertIn("Do not use Markdown.", prompt)
        self.assertIn("Do not wrap JSON in code fences.", prompt)
        self.assertIn("Do not invent requirements, policies, facts", prompt)
        self.assertIn(
            "- Feedback must be specific, actionable, respectful, and based on the answer.",
            prompt,
        )
        self.assertIn(
            "- passed must be true when score is at least 80% of max_score",
            prompt,
        )

    def test_identical_requests_produce_identical_prompt(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson",
            practical_task_title="Task",
            practical_task_description="Description.",
            expected_result="Result.",
            learner_answer="Answer.",
            criteria=(_sample_criterion(),),
        )

        first_prompt = self.builder.build(request)
        second_prompt = self.builder.build(request)

        self.assertEqual(first_prompt, second_prompt)

    def test_prompt_uses_explicit_russian_language(self) -> None:
        request = ReviewRequest(
            lesson_title="Урок",
            practical_task_title="Задание",
            practical_task_description="Описание.",
            expected_result="Результат.",
            learner_answer="Ответ.",
            criteria=(),
            language="ru",
        )

        prompt = self.builder.build(request)

        self.assertIn("- Language code: ru", prompt)
        self.assertIn("- Write all feedback strings in Russian.", prompt)
        self.assertIn(
            "- Do not reply in English unless the response language code is en.",
            prompt,
        )

    def test_prompt_uses_explicit_english_language(self) -> None:
        request = ReviewRequest(
            lesson_title="Lesson",
            practical_task_title="Task",
            practical_task_description="Description.",
            expected_result="Result.",
            learner_answer="Answer.",
            criteria=(),
            language="en",
        )

        prompt = self.builder.build(request)

        self.assertIn("- Language code: en", prompt)
        self.assertIn("- Write all feedback strings in English.", prompt)
        self.assertNotIn(
            "- Do not reply in English unless the response language code is en.",
            prompt,
        )

    def test_prompt_uses_explicit_kazakh_language(self) -> None:
        request = ReviewRequest(
            lesson_title="Сабақ",
            practical_task_title="Тапсырма",
            practical_task_description="Сипаттама.",
            expected_result="Нәтиже.",
            learner_answer="Жауап.",
            criteria=(),
            language="kk",
        )

        prompt = self.builder.build(request)

        self.assertIn("- Language code: kk", prompt)
        self.assertIn("- Write all feedback strings in Kazakh.", prompt)


if __name__ == "__main__":
    unittest.main()
