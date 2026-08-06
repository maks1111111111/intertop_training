"""Tests for OpenAI practical-task review provider."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.ai.client import DummyAIClient
from app.ai.config import OpenAIConfig
from app.ai.openai_review_provider import OpenAIPracticalTaskReviewer
from app.ai.review_interfaces import (
    ReviewFeedback,
    ReviewRequest,
    ReviewResult,
)
from app.ai.review_prompt_builder import ReviewPromptBuilder
from app.ai.review_response_parser import ReviewResponseParser
from app.ai.review_validator import ReviewValidationReport, ReviewValidator


def _sample_request() -> ReviewRequest:
    return ReviewRequest(
        lesson_title="Safety Basics",
        practical_task_title="Inspect the work area",
        practical_task_description="Walk through the area and identify hazards.",
        expected_result="All hazards are documented and addressed.",
        learner_answer="I checked the floor and removed loose cables.",
        criteria=(),
    )


def _sample_result() -> ReviewResult:
    return ReviewResult(
        score=8,
        max_score=10,
        passed=True,
        feedback=ReviewFeedback(
            summary="Strong answer with minor gaps.",
            strengths=("Identified hazards.",),
            improvements=("Document corrective actions.",),
        ),
    )


def _valid_report() -> ReviewValidationReport:
    return ReviewValidationReport(
        negative_scores=0,
        negative_max_scores=0,
        scores_above_maximum=0,
        invalid_passed_values=0,
        empty_feedback_summaries=0,
        empty_strengths=0,
        empty_improvements=0,
        valid=True,
    )


def _invalid_report() -> ReviewValidationReport:
    return ReviewValidationReport(
        negative_scores=1,
        negative_max_scores=0,
        scores_above_maximum=0,
        invalid_passed_values=0,
        empty_feedback_summaries=0,
        empty_strengths=0,
        empty_improvements=0,
        valid=False,
    )


class OpenAIPracticalTaskReviewerTests(unittest.TestCase):
    """Tests for :class:`OpenAIPracticalTaskReviewer`."""

    def test_model_is_stored(self) -> None:
        reviewer = OpenAIPracticalTaskReviewer(model="gpt-4o")

        self.assertEqual(reviewer._model, "gpt-4o")

    def test_injected_client_is_stored(self) -> None:
        injected_client = MagicMock()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=injected_client,
        )

        self.assertIs(reviewer._client, injected_client)

    def test_default_client_is_dummy_ai_client(self) -> None:
        reviewer = OpenAIPracticalTaskReviewer(model="gpt-4o")

        self.assertIsInstance(reviewer._client, DummyAIClient)

    def test_injected_prompt_builder_is_stored(self) -> None:
        injected_builder = MagicMock()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            prompt_builder=injected_builder,
        )

        self.assertIs(reviewer._prompt_builder, injected_builder)

    def test_injected_response_parser_is_stored(self) -> None:
        injected_parser = MagicMock()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            response_parser=injected_parser,
        )

        self.assertIs(reviewer._response_parser, injected_parser)

    def test_injected_validator_is_stored(self) -> None:
        injected_validator = MagicMock()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            validator=injected_validator,
        )

        self.assertIs(reviewer._validator, injected_validator)

    def test_default_prompt_builder_is_review_prompt_builder(self) -> None:
        reviewer = OpenAIPracticalTaskReviewer(model="gpt-4o")

        self.assertIsInstance(reviewer._prompt_builder, ReviewPromptBuilder)

    def test_default_response_parser_is_review_response_parser(self) -> None:
        reviewer = OpenAIPracticalTaskReviewer(model="gpt-4o")

        self.assertIsInstance(reviewer._response_parser, ReviewResponseParser)

    def test_default_validator_is_review_validator(self) -> None:
        reviewer = OpenAIPracticalTaskReviewer(model="gpt-4o")

        self.assertIsInstance(reviewer._validator, ReviewValidator)

    def test_review_calls_prompt_builder_once(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = '{"score": 8}'
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _valid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )
        request = _sample_request()

        reviewer.review(request)

        mock_prompt_builder.build.assert_called_once_with(request)

    def test_review_passes_prompt_builder_output_to_client(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = '{"score": 8}'
        mock_prompt_builder = MagicMock()
        expected_prompt = "Review prompt with task context."
        mock_prompt_builder.build.return_value = expected_prompt
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _valid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        reviewer.review(_sample_request())

        mock_client.generate.assert_called_once_with(expected_prompt)

    def test_review_passes_client_response_to_parser(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI review JSON."
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _valid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        reviewer.review(_sample_request())

        mock_parser.parse.assert_called_once_with("AI review JSON.")

    def test_review_passes_parser_result_to_validator(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI review JSON."
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        expected_result = _sample_result()
        mock_parser = MagicMock()
        mock_parser.parse.return_value = expected_result
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _valid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        reviewer.review(_sample_request())

        mock_validator.validate.assert_called_once_with(expected_result)

    def test_review_returns_parser_result_when_valid(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI review JSON."
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        expected_result = _sample_result()
        mock_parser = MagicMock()
        mock_parser.parse.return_value = expected_result
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _valid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        result = reviewer.review(_sample_request())

        self.assertIs(result, expected_result)

    def test_review_calls_components_in_order(self) -> None:
        call_order: list[str] = []
        mock_client = MagicMock()
        mock_client.generate.side_effect = (
            lambda prompt: call_order.append("client") or "response"
        )
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.side_effect = (
            lambda request: call_order.append("prompt_builder") or "prompt"
        )
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = (
            lambda response: call_order.append("parser") or _sample_result()
        )
        mock_validator = MagicMock()
        mock_validator.validate.side_effect = (
            lambda result: call_order.append("validator") or _valid_report()
        )
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        reviewer.review(_sample_request())

        self.assertEqual(
            call_order,
            ["prompt_builder", "client", "parser", "validator"],
        )

    def test_review_raises_value_error_when_validation_fails(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI review JSON."
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _invalid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(ValueError) as context:
            reviewer.review(_sample_request())

        self.assertEqual(
            str(context.exception),
            "AI review result failed validation.",
        )

    def test_invalid_report_does_not_modify_parser_result(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI review JSON."
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        expected_result = _sample_result()
        mock_parser = MagicMock()
        mock_parser.parse.return_value = expected_result
        mock_validator = MagicMock()
        mock_validator.validate.return_value = _invalid_report()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(ValueError):
            reviewer.review(_sample_request())

        self.assertIs(mock_parser.parse.return_value, expected_result)

    def test_client_exception_propagates(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.side_effect = RuntimeError("Client failed.")
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        mock_parser = MagicMock()
        mock_validator = MagicMock()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(RuntimeError) as context:
            reviewer.review(_sample_request())

        self.assertEqual(str(context.exception), "Client failed.")
        mock_parser.parse.assert_not_called()
        mock_validator.validate.assert_not_called()

    def test_parser_exception_propagates(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "invalid json"
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = ValueError("Invalid JSON.")
        mock_validator = MagicMock()
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(ValueError) as context:
            reviewer.review(_sample_request())

        self.assertEqual(str(context.exception), "Invalid JSON.")
        mock_validator.validate.assert_not_called()

    def test_validator_exception_propagates(self) -> None:
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI review JSON."
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build.return_value = "Review prompt."
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _sample_result()
        mock_validator = MagicMock()
        mock_validator.validate.side_effect = RuntimeError("Validator failed.")
        reviewer = OpenAIPracticalTaskReviewer(
            model="gpt-4o",
            client=mock_client,
            prompt_builder=mock_prompt_builder,
            response_parser=mock_parser,
            validator=mock_validator,
        )

        with self.assertRaises(RuntimeError) as context:
            reviewer.review(_sample_request())

        self.assertEqual(str(context.exception), "Validator failed.")


class OpenAIPracticalTaskReviewerFromConfigTests(unittest.TestCase):
    """Tests for :meth:`OpenAIPracticalTaskReviewer.from_config`."""

    @patch("app.ai.openai_review_provider.OpenAIClient")
    def test_from_config_creates_openai_client(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_client_instance = MagicMock()
        mock_openai_client_class.return_value = mock_client_instance

        reviewer = OpenAIPracticalTaskReviewer.from_config(config)

        mock_openai_client_class.assert_called_once_with(config)
        self.assertIs(reviewer._client, mock_client_instance)
        self.assertEqual(reviewer._model, "gpt-4o")

    @patch("app.ai.openai_review_provider.OpenAIClient")
    def test_from_config_uses_injected_client(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        injected_client = MagicMock()

        reviewer = OpenAIPracticalTaskReviewer.from_config(
            config,
            client=injected_client,
        )

        mock_openai_client_class.assert_not_called()
        self.assertIs(reviewer._client, injected_client)

    @patch("app.ai.openai_review_provider.OpenAIClient")
    def test_from_config_passes_injected_prompt_builder(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_openai_client_class.return_value = MagicMock()
        injected_builder = MagicMock()

        reviewer = OpenAIPracticalTaskReviewer.from_config(
            config,
            prompt_builder=injected_builder,
        )

        self.assertIs(reviewer._prompt_builder, injected_builder)

    @patch("app.ai.openai_review_provider.OpenAIClient")
    def test_from_config_passes_injected_response_parser(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_openai_client_class.return_value = MagicMock()
        injected_parser = MagicMock()

        reviewer = OpenAIPracticalTaskReviewer.from_config(
            config,
            response_parser=injected_parser,
        )

        self.assertIs(reviewer._response_parser, injected_parser)

    @patch("app.ai.openai_review_provider.OpenAIClient")
    def test_from_config_passes_injected_validator(
        self,
        mock_openai_client_class: MagicMock,
    ) -> None:
        config = OpenAIConfig(api_key="test-key", model="gpt-4o")
        mock_openai_client_class.return_value = MagicMock()
        injected_validator = MagicMock()

        reviewer = OpenAIPracticalTaskReviewer.from_config(
            config,
            validator=injected_validator,
        )

        self.assertIs(reviewer._validator, injected_validator)


if __name__ == "__main__":
    unittest.main()
