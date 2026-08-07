"""Telegram handlers for structured practical-task submission and AI review."""

from __future__ import annotations

import asyncio
import logging
from html import escape
from pathlib import Path
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.ai.review_interfaces import ReviewRequest, ReviewResult
from app.content.practical_task import PracticalTask
from app.content.runtime import ContentRuntime
from app.services.practical_task_review_flow_service import (
    PracticalTaskAttemptCreationError,
    PracticalTaskReviewCompletionError,
    PracticalTaskReviewFlowService,
)

logger = logging.getLogger(__name__)

router = Router()


class PracticalTaskStates(StatesGroup):
    """FSM states for practical-task answer submission."""

    waiting_for_answer = State()


def _parse_start_callback(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None
    if parts[0] != "practical_task" or parts[1] != "start":
        return None
    try:
        lesson_index = int(parts[3])
    except ValueError:
        return None
    return parts[2], lesson_index


def _parse_cancel_callback(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None
    if parts[0] != "practical_task" or parts[1] != "cancel":
        return None
    try:
        lesson_index = int(parts[3])
    except ValueError:
        return None
    return parts[2], lesson_index


def _format_task_start_text(task: PracticalTask) -> str:
    lines = [
        "🛠 <b>Практическое задание</b>",
        "",
        f"<b>{escape(task.title)}</b>",
        "",
        escape(task.description),
        "",
        f"🎯 Ожидаемый результат:\n{escape(task.expected_result)}",
    ]
    if task.estimated_minutes is not None:
        lines.extend(
            [
                "",
                f"⏱ Ориентировочное время: {task.estimated_minutes} мин.",
            ]
        )
    lines.extend(
        [
            "",
            "Напишите ваш ответ одним сообщением. "
            "После отправки ИИ проверит его и даст обратную связь.",
        ]
    )
    return "\n".join(lines)


def _format_review_result_text(result: ReviewResult) -> str:
    if result.passed:
        status_line = "✅ Задание выполнено"
    else:
        status_line = "❌ Нужно доработать"

    lines = [
        "🤖 <b>Проверка практического задания</b>",
        "",
        f"📊 Результат: {result.score} из {result.max_score}",
        "",
        status_line,
        "",
        "💬 <b>Обратная связь</b>",
        escape(result.feedback.summary),
    ]

    if result.feedback.strengths:
        lines.extend(["", "💪 <b>Сильные стороны</b>"])
        lines.extend(f"• {escape(item)}" for item in result.feedback.strengths)

    if result.feedback.improvements:
        lines.extend(["", "🔧 <b>Что улучшить</b>"])
        lines.extend(f"• {escape(item)}" for item in result.feedback.improvements)

    return "\n".join(lines)


def _task_start_keyboard(course_slug: str, lesson_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✖ Отменить",
                    callback_data=(
                        f"practical_task:cancel:{course_slug}:{lesson_index}"
                    ),
                )
            ]
        ]
    )


def _result_keyboard(course_slug: str, lesson_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Ответить ещё раз",
                    callback_data=(
                        f"practical_task:start:{course_slug}:{lesson_index}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Вернуться к уроку",
                    callback_data=f"lesson:{course_slug}:{lesson_index}",
                )
            ],
        ]
    )


@router.callback_query(F.data.startswith("practical_task:start:"))
async def start_practical_task(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    state: FSMContext,
    practical_task_review_flow: Optional[PracticalTaskReviewFlowService] = None,
) -> None:
    parsed = _parse_start_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return

    course_slug, lesson_index = parsed
    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    if lesson_index < 0 or lesson_index >= len(course.lessons):
        await callback.answer("Урок не найден.", show_alert=True)
        return

    lesson = course.lessons[lesson_index]
    task = lesson.structured_practical_task

    if task is None:
        await callback.answer(
            "Для этого урока нет практического задания.",
            show_alert=True,
        )
        return

    if callback.message is None:
        await callback.answer()
        return

    if practical_task_review_flow is None:
        await callback.answer(
            "AI-проверка практических заданий сейчас недоступна.",
            show_alert=True,
        )
        return

    await state.set_state(PracticalTaskStates.waiting_for_answer)
    await state.update_data(
        course_slug=course_slug,
        lesson_index=lesson_index,
    )

    await callback.message.answer(
        _format_task_start_text(task),
        parse_mode="HTML",
        reply_markup=_task_start_keyboard(course_slug, lesson_index),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("practical_task:cancel:"))
async def cancel_practical_task(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parsed = _parse_cancel_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return

    course_slug, lesson_index = parsed
    await state.clear()

    if callback.message is None:
        await callback.answer()
        return

    await callback.message.answer(
        "Отправка ответа отменена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📚 Вернуться к уроку",
                        callback_data=f"lesson:{course_slug}:{lesson_index}",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(PracticalTaskStates.waiting_for_answer)
async def receive_practical_task_answer(
    message: Message,
    content_runtime: ContentRuntime,
    db_path: Path,
    practical_task_review_flow: Optional[PracticalTaskReviewFlowService],
    state: FSMContext,
) -> None:
    if message.text is None:
        await message.answer(
            "Пожалуйста, отправьте ответ текстом одним сообщением."
        )
        return

    learner_answer = message.text.strip()
    if not learner_answer:
        await message.answer(
            "Ответ не может быть пустым. Напишите содержательный текст."
        )
        return

    data = await state.get_data()
    course_slug = data.get("course_slug")
    lesson_index = data.get("lesson_index")

    if not isinstance(course_slug, str) or not isinstance(lesson_index, int):
        await state.clear()
        await message.answer(
            "Не удалось определить задание. Откройте урок и начните заново."
        )
        return

    course = content_runtime.get_course(course_slug)
    if course is None:
        await state.clear()
        await message.answer("Курс не найден.")
        return

    if lesson_index < 0 or lesson_index >= len(course.lessons):
        await state.clear()
        await message.answer("Урок не найден.")
        return

    lesson = course.lessons[lesson_index]
    task = lesson.structured_practical_task

    if task is None:
        await state.clear()
        await message.answer("Для этого урока нет практического задания.")
        return

    if practical_task_review_flow is None:
        await state.clear()
        await message.answer(
            "AI-проверка практических заданий сейчас недоступна."
        )
        return

    review_request = ReviewRequest(
        lesson_title=lesson.title,
        practical_task_title=task.title,
        practical_task_description=task.description,
        expected_result=task.expected_result,
        learner_answer=learner_answer,
        criteria=(),
    )

    await message.answer("🤖 Проверяю ответ...")

    try:
        flow_result = await asyncio.to_thread(
            practical_task_review_flow.submit_and_review,
            db_path=db_path,
            telegram_id=message.from_user.id,
            course_slug=course_slug,
            lesson_slug=lesson.path.name,
            request=review_request,
        )
    except PracticalTaskAttemptCreationError:
        await state.clear()
        await message.answer(
            "Не удалось сохранить ответ. Попробуйте позже или обратитесь "
            "к администратору."
        )
        return
    except PracticalTaskReviewCompletionError:
        await state.clear()
        await message.answer(
            "Не удалось завершить AI-проверку. "
            "Попробуйте отправить ответ ещё раз позже."
        )
        return
    except Exception:
        logger.exception(
            "AI practical-task review failed for user_id=%s course=%s lesson=%s",
            message.from_user.id,
            course_slug,
            lesson.path.name,
        )
        await state.clear()
        await message.answer(
            "Не удалось завершить AI-проверку. "
            "Попробуйте отправить ответ ещё раз позже."
        )
        return

    await state.clear()

    await message.answer(
        _format_review_result_text(flow_result.review_result),
        parse_mode="HTML",
        reply_markup=_result_keyboard(course_slug, lesson_index),
    )
