"""OpenAI provider for practical-task review.

Wires together a review prompt builder, AI client, response parser, and
validator to implement :class:`PracticalTaskReviewerAI`.
"""

from __future__ import annotations

from typing import Optional

from app.ai.client import AIClient, DummyAIClient
from app.ai.config import OpenAIConfig
from app.ai.openai_client import OpenAIClient
from app.ai.review_interfaces import ReviewRequest, ReviewResult
from app.ai.review_prompt_builder import ReviewPromptBuilder
from app.ai.review_response_parser import ReviewResponseParser
from app.ai.review_validator import ReviewValidator


class OpenAIPracticalTaskReviewer:
    """OpenAI-backed implementation of :class:`PracticalTaskReviewerAI`."""

    def __init__(
        self,
        model: str,
        client: Optional[AIClient] = None,
        prompt_builder: Optional[ReviewPromptBuilder] = None,
        response_parser: Optional[ReviewResponseParser] = None,
        validator: Optional[ReviewValidator] = None,
    ) -> None:
        self._model = model
        self._client = client if client is not None else DummyAIClient()
        self._prompt_builder = (
            prompt_builder if prompt_builder is not None else ReviewPromptBuilder()
        )
        self._response_parser = (
            response_parser
            if response_parser is not None
            else ReviewResponseParser()
        )
        self._validator = (
            validator if validator is not None else ReviewValidator()
        )

    @classmethod
    def from_config(
        cls,
        config: OpenAIConfig,
        client: Optional[AIClient] = None,
        prompt_builder: Optional[ReviewPromptBuilder] = None,
        response_parser: Optional[ReviewResponseParser] = None,
        validator: Optional[ReviewValidator] = None,
    ) -> OpenAIPracticalTaskReviewer:
        """Create a reviewer wired with :class:`OpenAIClient` from *config*."""
        resolved_client = (
            client if client is not None else OpenAIClient(config)
        )
        return cls(
            model=config.model,
            client=resolved_client,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            validator=validator,
        )

    def review(
        self,
        request: ReviewRequest,
    ) -> ReviewResult:
        """Review a learner answer via OpenAI."""
        prompt = self._prompt_builder.build(request)
        response = self._client.generate(prompt)
        result = self._response_parser.parse(response)
        report = self._validator.validate(result)
        if not report.valid:
            raise ValueError("AI review result failed validation.")
        return result
