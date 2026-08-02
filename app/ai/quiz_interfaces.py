"""AI provider interfaces for quiz generation.

Defines request/result models and the protocol that all quiz AI backends
must implement. No concrete providers are included here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple

from app.content.lesson_builder import LessonCandidate


@dataclass(frozen=True)
class QuizOption:
    """A single answer option within a quiz question."""

    id: str
    text: str
    correct: bool


@dataclass(frozen=True)
class QuizQuestion:
    """A quiz question linked to a lesson."""

    id: str
    lesson: str
    question: str
    options: Tuple[QuizOption, ...]


@dataclass(frozen=True)
class GeneratedQuiz:
    """Structured quiz content produced by an AI backend."""

    title: str
    passing_score: int
    questions: Tuple[QuizQuestion, ...]


@dataclass(frozen=True)
class QuizGenerationRequest:
    """Input for AI quiz generation."""

    lessons: Tuple[LessonCandidate, ...]


@dataclass(frozen=True)
class QuizGenerationResult:
    """Output from AI quiz generation."""

    quiz: GeneratedQuiz


class QuizGenerationAI(Protocol):
    """Protocol for AI backends that generate quiz content."""

    def generate_quiz(
        self,
        request: QuizGenerationRequest,
    ) -> QuizGenerationResult:
        """Generate a quiz from the given request."""
        ...
