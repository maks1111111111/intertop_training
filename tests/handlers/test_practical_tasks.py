"""Tests for practical-task Telegram handlers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import ANY, AsyncMock, MagicMock, patch

from app.ai.review_interfaces import ReviewFeedback, ReviewRequest, ReviewResult
from app.content.practical_task import PracticalTask
from app.content.runtime_loader import Course, Lesson
from app.handlers.courses import _lesson_keyboard
from app.handlers import practical_tasks
from app.services.practical_task_review_flow_service import (
    PracticalTaskAttemptCreationError,
    PracticalTaskReviewCompletionError,
    PracticalTaskReviewFlowResult,
)


def _structured_task() -> PracticalTask:
    return PracticalTask(
        title="Inspect the work area",
        description="Walk through the area and identify hazards.",
        expected_result="All hazards are documented and addressed.",
        estimated_minutes=10,
    )


def _sample_lesson(**overrides: object) -> Lesson:
    defaults = {
        "path": Path("lesson_01"),
        "number": 1,
        "title": "Safety Basics",
        "description": "Main lesson text.",
        "image_path": None,
        "narration_path": None,
        "practical_task": "Legacy task string.",
        "structured_practical_task": _structured_task(),
        "checklist": (),
        "common_mistakes": (),
        "key_takeaways": (),
        "application_tips": (),
    }
    defaults.update(overrides)
    return Lesson(**defaults)


def _sample_course(*, lesson: Optional[Lesson] = None) -> Course:
    if lesson is None:
        lesson = _sample_lesson()
    return Course(
        slug="alpha",
        title="Alpha Course",
        status="published",
        version=1,
        lessons=[lesson],
        cover_path=None,
        quiz=None,
    )


def _sample_review_result(
    *,
    score: int = 8,
    max_score: int = 10,
    passed: bool = True,
    summary: str = "Good answer.",
    strengths: tuple[str, ...] = ("Identified hazards",),
    improvements: tuple[str, ...] = ("Add more detail",),
) -> ReviewResult:
    return ReviewResult(
        score=score,
        max_score=max_score,
        passed=passed,
        feedback=ReviewFeedback(
            summary=summary,
            strengths=strengths,
            improvements=improvements,
        ),
    )


class LessonKeyboardTests(unittest.TestCase):
    def test_structured_task_shows_submit_button(self) -> None:
        lesson = _sample_lesson()
        keyboard = _lesson_keyboard("alpha", 0, 1, lesson)
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("🛠 Выполнить практическое задание", labels)
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            "practical_task:start:alpha:0",
        )

    def test_lesson_without_structured_task_has_no_submit_button(self) -> None:
        lesson = _sample_lesson(structured_practical_task=None)
        keyboard = _lesson_keyboard("alpha", 0, 1, lesson)
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertNotIn("🛠 Выполнить практическое задание", labels)

    def test_legacy_practical_task_without_structured_has_no_submit_button(
        self,
    ) -> None:
        lesson = _sample_lesson(
            practical_task="Only legacy text.",
            structured_practical_task=None,
        )
        keyboard = _lesson_keyboard("alpha", 0, 1, lesson)
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertNotIn("🛠 Выполнить практическое задание", labels)

    def test_navigation_buttons_remain(self) -> None:
        lesson = _sample_lesson()
        keyboard = _lesson_keyboard("alpha", 0, 1, lesson)
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("✅ Завершить курс", labels)
        self.assertIn("← К списку курсов", labels)


class FormatReviewResultTests(unittest.TestCase):
    def test_html_special_characters_are_escaped(self) -> None:
        result = _sample_review_result(
            summary="<script>alert(1)</script>",
            strengths=("<b>bold</b>",),
            improvements=("use & improve",),
        )
        text = practical_tasks._format_review_result_text(result)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", text)
        self.assertIn("use &amp; improve", text)

    def test_passed_status_text(self) -> None:
        text = practical_tasks._format_review_result_text(
            _sample_review_result(passed=True),
        )
        self.assertIn("✅ Задание выполнено", text)

    def test_failed_status_text(self) -> None:
        text = practical_tasks._format_review_result_text(
            _sample_review_result(passed=False),
        )
        self.assertIn("❌ Нужно доработать", text)

    def test_empty_strengths_and_improvements_omitted(self) -> None:
        text = practical_tasks._format_review_result_text(
            _sample_review_result(strengths=(), improvements=()),
        )
        self.assertNotIn("💪", text)
        self.assertNotIn("🔧", text)


class StartPracticalTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_start_sets_fsm_and_sends_instructions(self) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        callback = MagicMock()
        callback.data = "practical_task:start:alpha:0"
        callback.message = AsyncMock()
        callback.answer = AsyncMock()

        state = AsyncMock()

        await practical_tasks.start_practical_task(
            callback,
            content_runtime=content_runtime,
            state=state,
            practical_task_review_flow=MagicMock(),
        )

        state.set_state.assert_awaited_once_with(
            practical_tasks.PracticalTaskStates.waiting_for_answer,
        )
        state.update_data.assert_awaited_once_with(
            course_slug="alpha",
            lesson_index=0,
        )
        callback.message.answer.assert_awaited_once()
        answer_kwargs = callback.message.answer.call_args.kwargs
        self.assertEqual(answer_kwargs["parse_mode"], "HTML")
        self.assertIn("Inspect the work area", callback.message.answer.call_args.args[0])
        callback.answer.assert_awaited_once()

    async def test_invalid_course_shows_alert(self) -> None:
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = None

        callback = MagicMock()
        callback.data = "practical_task:start:alpha:0"
        callback.answer = AsyncMock()

        state = AsyncMock()

        await practical_tasks.start_practical_task(
            callback,
            content_runtime=content_runtime,
            state=state,
            practical_task_review_flow=MagicMock(),
        )

        callback.answer.assert_awaited_once_with(
            "Курс не найден.",
            show_alert=True,
        )
        state.set_state.assert_not_called()

    async def test_invalid_lesson_index_shows_alert(self) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        callback = MagicMock()
        callback.data = "practical_task:start:alpha:5"
        callback.answer = AsyncMock()

        state = AsyncMock()

        await practical_tasks.start_practical_task(
            callback,
            content_runtime=content_runtime,
            state=state,
            practical_task_review_flow=MagicMock(),
        )

        callback.answer.assert_awaited_once_with(
            "Урок не найден.",
            show_alert=True,
        )

    async def test_lesson_without_structured_task_shows_alert(self) -> None:
        lesson = _sample_lesson(structured_practical_task=None)
        course = _sample_course(lesson=lesson)
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        callback = MagicMock()
        callback.data = "practical_task:start:alpha:0"
        callback.answer = AsyncMock()

        state = AsyncMock()

        await practical_tasks.start_practical_task(
            callback,
            content_runtime=content_runtime,
            state=state,
            practical_task_review_flow=MagicMock(),
        )

        callback.answer.assert_awaited_once_with(
            "Для этого урока нет практического задания.",
            show_alert=True,
        )

    async def test_start_when_ai_disabled_shows_alert_and_no_fsm(self) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        callback = MagicMock()
        callback.data = "practical_task:start:alpha:0"
        callback.message = AsyncMock()
        callback.answer = AsyncMock()

        state = AsyncMock()

        await practical_tasks.start_practical_task(
            callback,
            content_runtime=content_runtime,
            state=state,
            practical_task_review_flow=None,
        )

        callback.answer.assert_awaited_once_with(
            "AI-проверка практических заданий сейчас недоступна.",
            show_alert=True,
        )
        state.set_state.assert_not_called()
        callback.message.answer.assert_not_called()


class ReceivePracticalTaskAnswerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    async def test_successful_answer_calls_flow_and_clears_state(self) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        review_result = _sample_review_result()
        flow_service = MagicMock()
        flow_result = PracticalTaskReviewFlowResult(
            attempt_id=1,
            review_result=review_result,
        )

        message = MagicMock()
        message.text = "  I checked the floor.  "
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        with patch(
            "app.handlers.practical_tasks.asyncio.to_thread",
            new=AsyncMock(return_value=flow_result),
        ) as mock_to_thread:
            await practical_tasks.receive_practical_task_answer(
                message,
                content_runtime=content_runtime,
                db_path=self.db_path,
                practical_task_review_flow=flow_service,
                state=state,
            )

            mock_to_thread.assert_awaited_once_with(
                flow_service.submit_and_review,
                db_path=self.db_path,
                telegram_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                request=ANY,
            )

        request = mock_to_thread.call_args.kwargs["request"]
        self.assertIsInstance(request, ReviewRequest)
        self.assertEqual(request.lesson_title, "Safety Basics")
        self.assertEqual(request.practical_task_title, "Inspect the work area")
        self.assertEqual(
            request.learner_answer,
            "I checked the floor.",
        )
        self.assertEqual(request.criteria, ())

        state.clear.assert_awaited_once()
        final_answer = message.answer.call_args_list[-1]
        self.assertIn("8 из 10", final_answer.args[0])

    @patch("app.handlers.practical_tasks.asyncio.to_thread", new_callable=AsyncMock)
    async def test_successful_answer_uses_thread_boundary(
        self,
        mock_to_thread: AsyncMock,
    ) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        review_result = _sample_review_result()
        flow_service = MagicMock()
        mock_to_thread.return_value = PracticalTaskReviewFlowResult(
            attempt_id=1,
            review_result=review_result,
        )

        message = MagicMock()
        message.text = "Answer text."
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=content_runtime,
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        mock_to_thread.assert_awaited_once()
        self.assertIs(
            mock_to_thread.call_args.args[0],
            flow_service.submit_and_review,
        )
        state.clear.assert_awaited_once()
        self.assertIn(
            "8 из 10",
            message.answer.call_args_list[-1].args[0],
        )

    @patch("app.handlers.practical_tasks.logger")
    @patch("app.handlers.practical_tasks.asyncio.to_thread", new_callable=AsyncMock)
    async def test_exception_from_thread_boundary_is_handled(
        self,
        mock_to_thread: AsyncMock,
        mock_logger: MagicMock,
    ) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        flow_service = MagicMock()
        mock_to_thread.side_effect = RuntimeError("OpenAI down")

        message = MagicMock()
        message.text = "My answer."
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=content_runtime,
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        mock_to_thread.assert_awaited_once()
        mock_logger.exception.assert_called_once()
        state.clear.assert_awaited_once()

    async def test_disabled_ai_review_clears_state_without_calling_flow(
        self,
    ) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        flow_service = MagicMock()

        message = MagicMock()
        message.text = "My answer."
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=content_runtime,
            db_path=self.db_path,
            practical_task_review_flow=None,
            state=state,
        )

        flow_service.submit_and_review.assert_not_called()
        state.clear.assert_awaited_once()
        self.assertIn(
            "AI-проверка практических заданий сейчас недоступна.",
            message.answer.call_args_list[-1].args[0],
        )

    async def test_non_text_input_keeps_waiting_state(self) -> None:
        message = MagicMock()
        message.text = None
        message.answer = AsyncMock()

        state = AsyncMock()
        flow_service = MagicMock()

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=MagicMock(),
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        flow_service.submit_and_review.assert_not_called()
        state.clear.assert_not_called()

    async def test_empty_text_keeps_waiting_state(self) -> None:
        message = MagicMock()
        message.text = "   "
        message.answer = AsyncMock()

        state = AsyncMock()
        flow_service = MagicMock()

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=MagicMock(),
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        flow_service.submit_and_review.assert_not_called()
        state.clear.assert_not_called()

    @patch("app.handlers.practical_tasks.asyncio.to_thread", new_callable=AsyncMock)
    async def test_creation_error_clears_state(
        self,
        mock_to_thread: AsyncMock,
    ) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        flow_service = MagicMock()
        mock_to_thread.side_effect = PracticalTaskAttemptCreationError(
            "missing user"
        )

        message = MagicMock()
        message.text = "My answer."
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=content_runtime,
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        mock_to_thread.assert_awaited_once()
        state.clear.assert_awaited_once()
        self.assertIn(
            "Не удалось сохранить ответ",
            message.answer.call_args_list[-1].args[0],
        )

    @patch("app.handlers.practical_tasks.asyncio.to_thread", new_callable=AsyncMock)
    async def test_completion_error_clears_state(
        self,
        mock_to_thread: AsyncMock,
    ) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        flow_service = MagicMock()
        mock_to_thread.side_effect = PracticalTaskReviewCompletionError(
            "persist failed"
        )

        message = MagicMock()
        message.text = "My answer."
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=content_runtime,
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        mock_to_thread.assert_awaited_once()
        state.clear.assert_awaited_once()

    @patch("app.handlers.practical_tasks.logger")
    @patch("app.handlers.practical_tasks.asyncio.to_thread", new_callable=AsyncMock)
    async def test_generic_ai_error_is_logged_and_clears_state(
        self,
        mock_to_thread: AsyncMock,
        mock_logger: MagicMock,
    ) -> None:
        course = _sample_course()
        content_runtime = MagicMock()
        content_runtime.get_course.return_value = course

        flow_service = MagicMock()
        mock_to_thread.side_effect = RuntimeError("OpenAI down")

        message = MagicMock()
        message.text = "My answer."
        message.from_user = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"course_slug": "alpha", "lesson_index": 0},
        )

        await practical_tasks.receive_practical_task_answer(
            message,
            content_runtime=content_runtime,
            db_path=self.db_path,
            practical_task_review_flow=flow_service,
            state=state,
        )

        mock_to_thread.assert_awaited_once()
        mock_logger.exception.assert_called_once()
        state.clear.assert_awaited_once()


class CancelPracticalTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_clears_state(self) -> None:
        callback = MagicMock()
        callback.data = "practical_task:cancel:alpha:0"
        callback.message = AsyncMock()
        callback.answer = AsyncMock()

        state = AsyncMock()

        await practical_tasks.cancel_practical_task(callback, state=state)

        state.clear.assert_awaited_once()
        callback.message.answer.assert_awaited_once()
        self.assertIn(
            "Отправка ответа отменена.",
            callback.message.answer.call_args.args[0],
        )


if __name__ == "__main__":
    unittest.main()
