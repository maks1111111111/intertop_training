"""Structured practical task model for lesson content.

A :class:`PracticalTask` describes a hands-on exercise that learners
should complete after studying a lesson.  The model is intentionally
separate from the legacy ``practical_task`` string field on
:class:`~app.content.lesson_builder.LessonCandidate` so that future
pipeline stages can adopt structured tasks without breaking existing
courses or runtime contracts.

This module is foundation-only: nothing in Runtime, Telegram, AI parsing,
or file writers consumes :class:`PracticalTask` yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PracticalTask:
    """A structured practical exercise attached to a lesson.

    Attributes:
        title: Short name of the task shown to the learner.
        description: Instructions describing what the learner should do.
        expected_result: What a successful completion looks like.
        estimated_minutes: Optional time estimate in minutes.  ``None``
            means no estimate was provided.
    """

    title: str
    description: str
    expected_result: str
    estimated_minutes: Optional[int] = None
