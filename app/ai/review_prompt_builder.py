"""Prompt builder for AI practical-task review.

Assembles deterministic text prompts from review requests.
No LLM calls or external dependencies are used here.
"""

from __future__ import annotations

from app.ai.review_interfaces import ReviewCriterion, ReviewRequest
from app.ai.review_language import normalize_review_language

_LANGUAGE_LABELS = {
    "ru": "Russian",
    "kk": "Kazakh",
    "en": "English",
}


def _language_instruction_lines(language: str) -> list[str]:
    label = _LANGUAGE_LABELS.get(language, language)
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


class ReviewPromptBuilder:
    """Build text prompts for AI review of practical-task answers."""

    def build(self, request: ReviewRequest) -> str:
        """Build a prompt for evaluating a learner's practical-task answer.

        Args:
            request: Review input including task context and scoring criteria.

        Returns:
            A deterministic review prompt.
        """
        language = normalize_review_language(request.language) or "ru"

        lines = [
            "You are an objective reviewer of a learner's practical-task answer.",
            "Evaluate only against the supplied task, expected result, and criteria.",
            "Do not invent requirements, policies, facts, or missing source information.",
            "Do not reward information unrelated to the task.",
            *_language_instruction_lines(language),
            "",
            "Lesson context:",
            request.lesson_title,
            "",
            "Practical task:",
            f"Title: {request.practical_task_title}",
            "",
            "Instructions:",
            request.practical_task_description,
            "",
            "Expected result:",
            request.expected_result,
            "",
            "Evaluation criteria:",
        ]

        if request.criteria:
            total_max_score = sum(criterion.max_score for criterion in request.criteria)
            for index, criterion in enumerate(request.criteria, start=1):
                lines.extend(_format_criterion(index, criterion))
            lines.extend(
                [
                    "",
                    (
                        "The maximum score is the sum of criterion scores: "
                        f"{total_max_score}."
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "No additional criteria were provided.",
                    (
                        "Evaluate the answer only against the practical task and "
                        "expected result above."
                    ),
                    "The maximum score for this review is 100.",
                ]
            )

        lines.extend(
            [
                "",
                "Learner answer:",
                request.learner_answer,
                "",
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
                "",
                "Scoring rules:",
                "- score must be an integer from 0 to max_score.",
            ]
        )

        if request.criteria:
            total_max_score = sum(criterion.max_score for criterion in request.criteria)
            lines.append(
                (
                    "- max_score must be "
                    f"{total_max_score} (sum of all criterion maximum scores)."
                )
            )
        else:
            lines.append("- max_score must be 100.")

        lines.extend(
            [
                (
                    "- passed must be true when score is at least 80% of max_score; "
                    "otherwise false."
                ),
                "- feedback.summary must briefly explain the overall evaluation.",
                (
                    "- feedback.strengths must list specific elements the learner "
                    "did well."
                ),
                (
                    "- feedback.improvements must list concrete gaps or next steps."
                ),
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
        )

        return "\n".join(lines).rstrip("\n")


def _format_criterion(index: int, criterion: ReviewCriterion) -> list[str]:
    return [
        "",
        f"Criterion {index}:",
        f"ID: {criterion.id}",
        f"Title: {criterion.title}",
        f"Description: {criterion.description}",
        f"Maximum score: {criterion.max_score}",
    ]
