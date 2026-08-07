"""Tests for quiz Telegram handlers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.content.runtime_loader import (
    Course,
    Quiz,
    QuizOption,
    QuizQuestion,
)
from app.handlers.quiz import answer_quiz


def _sample_quiz(*, question_count: int = 2) -> Quiz:
    questions = [
        QuizQuestion(
            id=f"q{index + 1}",
            question_type="single_choice",
            text=f"Question {index + 1}?",
            options=[
                QuizOption(id="a", text="Option A"),
                QuizOption(id="b", text="Option B"),
            ],
            correct_option_ids=["a"],
            explanation="Because A is correct.",
            lesson="lesson_01",
            difficulty=1,
            tags=[],
            ai_context="",
        )
        for index in range(question_count)
    ]
    return Quiz(
        id="alpha_quiz",
        title="Alpha Quiz",
        passing_score=80,
        questions=questions,
        version=1,
        randomize_questions=False,
        randomize_options=False,
    )


def _sample_course(*, quiz: Quiz | None = None) -> Course:
    return Course(
        slug="alpha",
        title="Alpha Course",
        status="published",
        version=1,
        lessons=[],
        cover_path=None,
        quiz=quiz if quiz is not None else _sample_quiz(),
    )


def _build_callback(
    *,
    data: str = "quiz_answer:alpha:0:a",
    telegram_id: int = 1001,
) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.from_user = MagicMock()
    callback.from_user.id = telegram_id
    callback.message = AsyncMock()
    callback.answer = AsyncMock()
    return callback


class AnswerQuizHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        self.content_runtime = MagicMock()
        self.content_runtime.get_course.return_value = _sample_course()

    async def asyncTearDown(self) -> None:
        self._tmpdir.cleanup()

    @patch("app.handlers.quiz.quiz_repository")
    async def test_first_answer_shows_result_and_clears_keyboard(
        self,
        mock_repository: MagicMock,
    ) -> None:
        mock_repository.get_active_attempt.return_value = {"id": 1}
        mock_repository.save_answer.return_value = True
        callback = _build_callback()

        await answer_quiz(callback, self.content_runtime, self.db_path)

        mock_repository.save_answer.assert_called_once_with(
            db_path=self.db_path,
            attempt_id=1,
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        callback.message.edit_reply_markup.assert_awaited_once_with(
            reply_markup=None,
        )
        callback.message.answer.assert_awaited_once()
        callback.answer.assert_awaited_once()

    @patch("app.handlers.quiz.quiz_repository")
    async def test_duplicate_answer_shows_alert_without_second_result(
        self,
        mock_repository: MagicMock,
    ) -> None:
        mock_repository.get_active_attempt.return_value = {"id": 1}
        mock_repository.save_answer.return_value = False
        callback = _build_callback()

        await answer_quiz(callback, self.content_runtime, self.db_path)

        mock_repository.save_answer.assert_called_once()
        callback.answer.assert_awaited_once_with(
            "Ответ на этот вопрос уже принят.",
            show_alert=True,
        )
        callback.message.edit_reply_markup.assert_not_awaited()
        callback.message.answer.assert_not_awaited()

    @patch("app.handlers.quiz.quiz_repository")
    async def test_invalid_option_does_not_save_answer(
        self,
        mock_repository: MagicMock,
    ) -> None:
        mock_repository.get_active_attempt.return_value = {"id": 1}
        callback = _build_callback(data="quiz_answer:alpha:0:missing")

        await answer_quiz(callback, self.content_runtime, self.db_path)

        mock_repository.save_answer.assert_not_called()
        callback.answer.assert_awaited_once_with(
            "Некорректный вариант ответа.",
            show_alert=True,
        )

    @patch("app.handlers.quiz.quiz_repository")
    async def test_missing_course_does_not_save_answer(
        self,
        mock_repository: MagicMock,
    ) -> None:
        self.content_runtime.get_course.return_value = None
        callback = _build_callback()

        await answer_quiz(callback, self.content_runtime, self.db_path)

        mock_repository.get_active_attempt.assert_not_called()
        mock_repository.save_answer.assert_not_called()
        callback.answer.assert_awaited_once_with(
            "Курс не найден.",
            show_alert=True,
        )

    @patch("app.handlers.quiz.quiz_repository")
    async def test_invalid_question_index_does_not_save_answer(
        self,
        mock_repository: MagicMock,
    ) -> None:
        callback = _build_callback(data="quiz_answer:alpha:99:a")

        await answer_quiz(callback, self.content_runtime, self.db_path)

        mock_repository.save_answer.assert_not_called()
        callback.answer.assert_awaited_once_with(
            "Вопрос не найден.",
            show_alert=True,
        )


if __name__ == "__main__":
    unittest.main()
