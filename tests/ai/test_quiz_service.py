"""Tests for AI quiz service layer (``app.ai.quiz_service``)."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from app.ai.client import AIClient
from app.ai.quiz_coverage import (
    create_quiz_generation_request,
    lesson_slug_for_index,
    resolve_lesson_question_targets,
)
from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationRequest,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.ai.quiz_prompt_builder import QuizPromptBuilder
from app.ai.quiz_response_parser import QuizResponseParser
from app.ai.quiz_service import QuizGenerationService
from app.content.lesson_builder import LessonCandidate


def _valid_quiz_json_for_request(request: QuizGenerationRequest) -> str:
    targets = resolve_lesson_question_targets(request)
    questions: List[Dict[str, Any]] = []
    question_number = 1

    for lesson_index, required_count in enumerate(targets, start=1):
        lesson_slug = lesson_slug_for_index(lesson_index)
        for _ in range(required_count):
            questions.append(
                {
                    "id": f"q{question_number}",
                    "lesson": lesson_slug,
                    "question": f"Question {question_number}?",
                    "options": [
                        {"id": "a", "text": "Correct answer", "correct": True},
                        {"id": "b", "text": "Incorrect answer 1", "correct": False},
                        {"id": "c", "text": "Incorrect answer 2", "correct": False},
                        {"id": "d", "text": "Incorrect answer 3", "correct": False},
                    ],
                }
            )
            question_number += 1

    payload: Dict[str, Any] = {
        "title": "Final course quiz",
        "passing_score": 80,
        "questions": questions,
    }
    return json.dumps(payload)


def _sample_request(
    lessons: Optional[List[LessonCandidate]] = None,
) -> QuizGenerationRequest:
    if lessons is None:
        lessons = [
            LessonCandidate(
                title="Safety basics",
                content="Always wear protective equipment.",
            )
        ]
    return create_quiz_generation_request(tuple(lessons))


class QuizGenerationServiceTests(unittest.TestCase):
    """Tests for :class:`QuizGenerationService`."""

    def test_successful_generation(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = _valid_quiz_json_for_request(request)
        service = QuizGenerationService(provider)

        result = service.generate_quiz(request)

        self.assertIsInstance(result, QuizGenerationResult)
        self.assertEqual(result.quiz.title, "Final course quiz")
        self.assertEqual(result.quiz.passing_score, 80)
        self.assertEqual(len(result.quiz.questions), 2)

    def test_prompt_passed_to_ai_provider(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = _valid_quiz_json_for_request(request)
        prompt_builder = MagicMock(spec=QuizPromptBuilder)
        expected_prompt = "Create a final course quiz."
        prompt_builder.build_quiz_generation_prompt.return_value = expected_prompt
        service = QuizGenerationService(provider, prompt_builder=prompt_builder)

        service.generate_quiz(request)

        provider.generate.assert_called_once_with(expected_prompt)

    def test_prompt_builder_receives_request(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = _valid_quiz_json_for_request(request)
        prompt_builder = MagicMock(spec=QuizPromptBuilder)
        prompt_builder.build_quiz_generation_prompt.return_value = "Prompt text."
        service = QuizGenerationService(provider, prompt_builder=prompt_builder)

        service.generate_quiz(request)

        prompt_builder.build_quiz_generation_prompt.assert_called_once_with(request)

    def test_parser_used_with_ai_response(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        ai_response = _valid_quiz_json_for_request(request)
        provider.generate.return_value = ai_response
        response_parser = MagicMock(spec=QuizResponseParser)
        expected_result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Parsed quiz",
                passing_score=80,
                questions=tuple(
                    QuizQuestion(
                        id=f"q{index}",
                        lesson="lesson_01",
                        question=f"Sample {index}?",
                        options=(
                            QuizOption(id="a", text="Yes", correct=True),
                            QuizOption(id="b", text="No", correct=False),
                            QuizOption(id="c", text="Maybe", correct=False),
                            QuizOption(id="d", text="Never", correct=False),
                        ),
                    )
                    for index in range(1, 3)
                ),
            )
        )
        response_parser.parse_quiz.return_value = expected_result
        service = QuizGenerationService(
            provider,
            response_parser=response_parser,
        )

        service.generate_quiz(request)

        response_parser.parse_quiz.assert_called_once_with(ai_response)

    @patch("app.ai.quiz_service.validate_quiz_coverage")
    def test_returns_parser_result_unchanged(
        self,
        mock_validate: MagicMock,
    ) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = _valid_quiz_json_for_request(request)
        response_parser = MagicMock(spec=QuizResponseParser)
        expected_result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Parsed quiz",
                passing_score=90,
                questions=(),
            )
        )
        response_parser.parse_quiz.return_value = expected_result
        service = QuizGenerationService(
            provider,
            response_parser=response_parser,
        )

        result = service.generate_quiz(request)

        self.assertIs(result, expected_result)
        mock_validate.assert_called_once_with(request, expected_result)

    def test_empty_lessons_builds_empty_prompt(self) -> None:
        provider = MagicMock(spec=AIClient)
        prompt_builder = MagicMock(spec=QuizPromptBuilder)
        prompt_builder.build_quiz_generation_prompt.return_value = ""
        response_parser = MagicMock(spec=QuizResponseParser)
        service = QuizGenerationService(
            provider,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
        )
        request = QuizGenerationRequest(lessons=())

        with self.assertRaisesRegex(
            ValueError,
            "Quiz generation prompt must not be empty.",
        ):
            service.generate_quiz(request)

        prompt_builder.build_quiz_generation_prompt.assert_called_once_with(request)
        provider.generate.assert_not_called()
        response_parser.parse_quiz.assert_not_called()

    def test_ai_exception_propagates(self) -> None:
        provider = MagicMock(spec=AIClient)
        provider.generate.side_effect = RuntimeError("AI backend failed.")
        service = QuizGenerationService(provider)
        request = _sample_request()

        with self.assertRaises(RuntimeError):
            service.generate_quiz(request)

    def test_parser_exception_propagates(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = "not valid json"
        response_parser = MagicMock(spec=QuizResponseParser)
        response_parser.parse_quiz.side_effect = ValueError("Invalid quiz JSON.")
        service = QuizGenerationService(
            provider,
            response_parser=response_parser,
        )

        with self.assertRaises(ValueError):
            service.generate_quiz(request)

    def test_component_call_order(self) -> None:
        call_log: List[str] = []
        provider = MagicMock(spec=AIClient)
        request = _sample_request()

        def record_generate(prompt: str) -> str:
            call_log.append("provider")
            return _valid_quiz_json_for_request(request)

        provider.generate.side_effect = record_generate

        prompt_builder = MagicMock(spec=QuizPromptBuilder)

        def record_build(build_request: QuizGenerationRequest) -> str:
            call_log.append("prompt_builder")
            return "Prompt."

        prompt_builder.build_quiz_generation_prompt.side_effect = record_build

        response_parser = MagicMock(spec=QuizResponseParser)

        def record_parse(response: str) -> QuizGenerationResult:
            call_log.append("parser")
            return QuizResponseParser().parse_quiz(response)

        response_parser.parse_quiz.side_effect = record_parse

        service = QuizGenerationService(
            provider,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
        )

        service.generate_quiz(request)

        self.assertEqual(call_log, ["prompt_builder", "provider", "parser"])

    def test_default_prompt_builder_and_parser(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = _valid_quiz_json_for_request(request)
        service = QuizGenerationService(provider)

        result = service.generate_quiz(request)

        self.assertIsInstance(service._prompt_builder, QuizPromptBuilder)
        self.assertIsInstance(service._response_parser, QuizResponseParser)
        self.assertIsInstance(result, QuizGenerationResult)

    def test_under_delivered_quiz_raises(self) -> None:
        provider = MagicMock(spec=AIClient)
        request = _sample_request()
        provider.generate.return_value = _valid_quiz_json_for_request(request)
        response_parser = MagicMock(spec=QuizResponseParser)
        response_parser.parse_quiz.return_value = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Too small",
                passing_score=80,
                questions=(
                    QuizQuestion(
                        id="q1",
                        lesson="lesson_01",
                        question="Only one?",
                        options=(
                            QuizOption(id="a", text="Yes", correct=True),
                            QuizOption(id="b", text="No", correct=False),
                            QuizOption(id="c", text="Maybe", correct=False),
                            QuizOption(id="d", text="Never", correct=False),
                        ),
                    ),
                ),
            )
        )
        service = QuizGenerationService(
            provider,
            response_parser=response_parser,
        )

        with self.assertRaisesRegex(
            ValueError,
            "Generated quiz contains 1 questions, but exactly 2 were required.",
        ):
            service.generate_quiz(request)


if __name__ == "__main__":
    unittest.main()
