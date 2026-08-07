"""AI reviewer data contracts.

Defines request/result models for evaluating learner answers to practical
tasks. No concrete review providers or business logic are included here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple


@dataclass(frozen=True)
class ReviewCriterion:
    """A single scoring criterion for practical-task review."""

    id: str
    title: str
    description: str
    max_score: int


@dataclass(frozen=True)
class ReviewFeedback:
    """Structured qualitative feedback from a review."""

    summary: str
    strengths: Tuple[str, ...]
    improvements: Tuple[str, ...]


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of reviewing a learner answer."""

    score: int
    max_score: int
    passed: bool
    feedback: ReviewFeedback


@dataclass(frozen=True)
class ReviewRequest:
    """Input for AI review of a practical-task answer."""

    lesson_title: str
    practical_task_title: str
    practical_task_description: str
    expected_result: str
    learner_answer: str
    criteria: Tuple[ReviewCriterion, ...]
    language: str = "ru"


class PracticalTaskReviewerAI(Protocol):
    """Protocol for AI backends that review practical-task answers."""

    def review(
        self,
        request: ReviewRequest,
    ) -> ReviewResult:
        """Review a learner answer and return structured feedback."""
        ...
