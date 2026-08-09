"""AI provider interfaces for practical-task generation."""

from __future__ import annotations

from dataclasses import dataclass

from app.content.lesson_builder import LessonCandidate
from app.content.practical_task import PracticalTask


@dataclass(frozen=True)
class PracticalTaskGenerationRequest:
    """Input for AI practical-task generation from one lesson."""

    lesson: LessonCandidate


@dataclass(frozen=True)
class PracticalTaskGenerationResult:
    """Output from AI practical-task generation."""

    task: PracticalTask
