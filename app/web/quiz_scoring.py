"""Server-side quiz scoring for the read-only Web UI."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from app.content.runtime_loader import Quiz, QuizOption, QuizQuestion


@dataclass(frozen=True)
class QuizOptionView:
    """One answer option shown in the quiz form."""

    id: str
    text: str


@dataclass(frozen=True)
class QuizQuestionView:
    """One question prepared for HTML rendering."""

    id: str
    text: str
    options: tuple[QuizOptionView, ...]


@dataclass(frozen=True)
class QuizPageView:
    """Quiz metadata and questions for the Web quiz page."""

    title: str
    questions_count: int
    passing_score: int
    questions: tuple[QuizQuestionView, ...]


@dataclass(frozen=True)
class QuizQuestionReviewView:
    """Per-question review shown after submission."""

    question_text: str
    selected_option_text: Optional[str]
    is_correct: bool


@dataclass(frozen=True)
class WebQuizResult:
    """Outcome of a Web quiz submission."""

    score_percent: float
    correct_answers: int
    questions_count: int
    passing_score: int
    passed: bool
    reviews: tuple[QuizQuestionReviewView, ...]


@dataclass(frozen=True)
class QuizSummaryView:
    """Short quiz info for the course detail page."""

    title: str
    questions_count: int
    passing_score: int


def format_score_percent(value: float) -> str:
    """Format a score percentage for display."""
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def ordered_question_options(
    question: QuizQuestion,
    randomize_options: bool,
) -> tuple[QuizOption, ...]:
    """Return question options in display order."""
    options = list(question.options)
    if randomize_options:
        random.shuffle(options)
    return tuple(options)


def build_quiz_page_view(quiz: Quiz) -> QuizPageView:
    """Build a presentation model for the quiz form page."""
    questions = tuple(
        QuizQuestionView(
            id=question.id,
            text=question.text,
            options=tuple(
                QuizOptionView(id=option.id, text=option.text)
                for option in ordered_question_options(
                    question,
                    quiz.randomize_options,
                )
            ),
        )
        for question in quiz.questions
    )
    return QuizPageView(
        title=quiz.title,
        questions_count=len(questions),
        passing_score=quiz.passing_score,
        questions=questions,
    )


def build_quiz_summary_view(quiz: Quiz) -> QuizSummaryView:
    """Build short quiz metadata for the course page."""
    return QuizSummaryView(
        title=quiz.title,
        questions_count=len(quiz.questions),
        passing_score=quiz.passing_score,
    )


def _option_ids(question: QuizQuestion) -> set[str]:
    return {option.id for option in question.options}


def _find_option_text(question: QuizQuestion, option_id: str) -> Optional[str]:
    for option in question.options:
        if option.id == option_id:
            return option.text
    return None


def _is_answer_correct(question: QuizQuestion, option_id: Optional[str]) -> bool:
    if option_id is None:
        return False
    if option_id not in _option_ids(question):
        return False
    return option_id in question.correct_option_ids


def score_web_quiz(quiz: Quiz, answers: dict[str, str]) -> WebQuizResult:
    """Score submitted answers against the runtime quiz definition."""
    questions_count = len(quiz.questions)
    if questions_count == 0:
        return WebQuizResult(
            score_percent=0.0,
            correct_answers=0,
            questions_count=0,
            passing_score=quiz.passing_score,
            passed=False,
            reviews=(),
        )

    correct_answers = 0
    reviews: list[QuizQuestionReviewView] = []

    for question in quiz.questions:
        selected_option_id = answers.get(question.id)
        if selected_option_id == "":
            selected_option_id = None
        is_correct = _is_answer_correct(question, selected_option_id)
        if is_correct:
            correct_answers += 1

        selected_text: Optional[str] = None
        if selected_option_id is not None:
            selected_text = _find_option_text(question, selected_option_id)

        reviews.append(
            QuizQuestionReviewView(
                question_text=question.text,
                selected_option_text=selected_text,
                is_correct=is_correct,
            )
        )

    score_percent = round(correct_answers * 100 / questions_count, 2)
    if score_percent > 100.0:
        score_percent = 100.0
    passed = score_percent >= quiz.passing_score

    return WebQuizResult(
        score_percent=score_percent,
        correct_answers=correct_answers,
        questions_count=questions_count,
        passing_score=quiz.passing_score,
        passed=passed,
        reviews=tuple(reviews),
    )
