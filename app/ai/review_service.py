"""AI service layer for practical-task review.

Provides a single entry point for reviewing learner answers that delegates
to a pluggable :class:`PracticalTaskReviewerAI` provider.
"""

from __future__ import annotations

from app.ai.review_interfaces import (
    PracticalTaskReviewerAI,
    ReviewRequest,
    ReviewResult,
)


class PracticalTaskReviewService:
    """Application service that delegates practical-task review to an AI provider."""

    def __init__(
        self,
        provider: PracticalTaskReviewerAI,
    ) -> None:
        self._provider = provider

    def review(
        self,
        request: ReviewRequest,
    ) -> ReviewResult:
        """Review a learner answer via the configured AI provider."""
        return self._provider.review(request)
