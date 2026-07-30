import sqlite3
from pathlib import Path
from typing import Optional

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from app.content.runtime import ContentRuntime
from app.repositories import quiz_repository
from app.services.scanner import Quiz, QuizQuestion


router = Router()


def _quiz_question_text(
    quiz: Quiz,
    question_index: int,
) -> str:
    question = quiz.questions[question_index]
    questions_count = len(quiz.questions)

    return (
        f"📝 {quiz.title}\n\n"
        f"Вопрос {question_index + 1} из {questions_count}\n\n"
        f"{question.text}"
    )


def _quiz_question_keyboard(
    course_slug: str,
    question_index: int,
    question: QuizQuestion,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    for option in question.options:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=option.text,
                    callback_data=(
                        f"quiz_answer:{course_slug}:{question_index}:{option.id}"
                    ),
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _quiz_answer_result_text(
    question: QuizQuestion,
    option_id: str,
) -> str:
    if option_id in question.correct_option_ids:
        text = "✅ Верно!"
    else:
        text = "❌ Неверно."

    if question.explanation:
        text = f"{text}\n\n{question.explanation}"

    return text


def _quiz_answer_result_keyboard(
    course_slug: str,
    question_index: int,
    questions_count: int,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    if question_index < questions_count - 1:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Следующий вопрос →",
                    callback_data=f"quiz_next:{course_slug}:{question_index + 1}",
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🏁 Завершить тест",
                    callback_data=f"quiz_finish:{course_slug}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_score_percent(score_percent: float) -> str:
    if score_percent == int(score_percent):
        return str(int(score_percent))
    return f"{score_percent:.2f}".rstrip("0").rstrip(".")


def _format_course_quiz_stats(stats: quiz_repository.CourseQuizStats) -> str:
    lines = [
        "📚 Общая статистика",
        "",
        f"🔢 Попыток: {stats['attempts_count']}",
    ]

    if stats["attempts_count"] > 1:
        best_score_percent = stats["best_score_percent"]
        if best_score_percent is not None:
            lines.append(
                f"🏆 Лучший результат: {_format_score_percent(best_score_percent)}%"
            )

        average_score_percent = stats["average_score_percent"]
        if average_score_percent is not None:
            lines.append(
                f"📈 Средний результат: {_format_score_percent(average_score_percent)}%"
            )

    return "\n".join(lines)


def _quiz_finish_result_text(
    attempt: sqlite3.Row,
    stats: Optional[quiz_repository.CourseQuizStats] = None,
) -> str:
    correct_answers = int(attempt["correct_answers"])
    questions_count = int(attempt["questions_count"])
    score_percent = float(attempt["score_percent"])
    passed = bool(attempt["passed"])

    text = (
        "🏁 Тест завершён!\n\n"
        "📊 Ваш результат\n\n"
        f"✅ Правильных ответов: {correct_answers} из {questions_count}\n"
        f"📈 Процент: {_format_score_percent(score_percent)}%"
    )

    if passed:
        text = f"{text}\n\n🎉 Статус: СДАН"
    else:
        text = f"{text}\n\n❌ Статус: НЕ СДАН"

    if stats is not None and stats["attempts_count"] > 0:
        text = f"{text}\n\n{_format_course_quiz_stats(stats)}"

    return text


def _quiz_finish_result_keyboard(course_slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Пройти ещё раз",
                    callback_data=f"quiz_start:{course_slug}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 К курсу",
                    callback_data=f"course_card:{course_slug}",
                )
            ],
        ]
    )


@router.callback_query(F.data.startswith("quiz_start:"))
async def start_quiz(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    course_slug = callback.data.removeprefix("quiz_start:")
    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    if course.quiz is None:
        await callback.answer(
            "Для этого курса тест пока недоступен.",
            show_alert=True,
        )
        return

    if not course.quiz.questions:
        await callback.answer("Тест пока пуст.", show_alert=True)
        return

    if callback.message is None:
        await callback.answer()
        return

    quiz_repository.create_attempt(
        db_path=db_path,
        telegram_id=callback.from_user.id,
        course_slug=course_slug,
        quiz_version=course.quiz.version,
        questions_count=len(course.quiz.questions),
    )

    question_index = 0
    question = course.quiz.questions[question_index]

    await callback.message.answer(
        _quiz_question_text(course.quiz, question_index),
        reply_markup=_quiz_question_keyboard(
            course_slug=course_slug,
            question_index=question_index,
            question=question,
        ),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("quiz_answer:"))
async def answer_quiz(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Некорректная команда.",
            show_alert=True,
        )
        return

    _, course_slug, question_index_raw, option_id = parts

    try:
        question_index = int(question_index_raw)
    except ValueError:
        await callback.answer(
            "Некорректный номер вопроса.",
            show_alert=True,
        )
        return

    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    if course.quiz is None:
        await callback.answer(
            "Для этого курса тест пока недоступен.",
            show_alert=True,
        )
        return

    quiz = course.quiz

    if question_index < 0 or question_index >= len(quiz.questions):
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    question = quiz.questions[question_index]

    if not any(option.id == option_id for option in question.options):
        await callback.answer(
            "Некорректный вариант ответа.",
            show_alert=True,
        )
        return

    if callback.message is None:
        await callback.answer()
        return

    attempt = quiz_repository.get_active_attempt(
        db_path=db_path,
        telegram_id=callback.from_user.id,
        course_slug=course_slug,
    )

    if attempt is not None:
        is_correct = option_id in question.correct_option_ids
        quiz_repository.save_answer(
            db_path=db_path,
            attempt_id=int(attempt["id"]),
            question_id=question.id,
            selected_option_id=option_id,
            is_correct=is_correct,
        )

    await callback.message.answer(
        _quiz_answer_result_text(question, option_id),
        reply_markup=_quiz_answer_result_keyboard(
            course_slug=course_slug,
            question_index=question_index,
            questions_count=len(quiz.questions),
        ),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("quiz_next:"))
async def next_quiz_question(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "Некорректная команда.",
            show_alert=True,
        )
        return

    _, course_slug, question_index_raw = parts

    try:
        question_index = int(question_index_raw)
    except ValueError:
        await callback.answer(
            "Некорректный номер вопроса.",
            show_alert=True,
        )
        return

    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    if course.quiz is None:
        await callback.answer(
            "Для этого курса тест пока недоступен.",
            show_alert=True,
        )
        return

    if question_index < 0 or question_index >= len(course.quiz.questions):
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    if callback.message is None:
        await callback.answer()
        return

    question = course.quiz.questions[question_index]

    await callback.message.answer(
        _quiz_question_text(course.quiz, question_index),
        reply_markup=_quiz_question_keyboard(
            course_slug=course_slug,
            question_index=question_index,
            question=question,
        ),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("quiz_finish:"))
async def finish_quiz(
    callback: CallbackQuery,
    db_path: Path,
) -> None:
    course_slug = callback.data.removeprefix("quiz_finish:")

    attempt = quiz_repository.get_active_attempt(
        db_path=db_path,
        telegram_id=callback.from_user.id,
        course_slug=course_slug,
    )

    attempt_id: int | None = None
    if attempt is not None:
        attempt_id = int(attempt["id"])
        quiz_repository.finish_attempt(
            db_path=db_path,
            attempt_id=attempt_id,
        )

    if callback.message is None:
        await callback.answer()
        return

    keyboard = _quiz_finish_result_keyboard(course_slug)

    if attempt_id is None:
        await callback.message.answer(
            "🏁 Тест завершён!",
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    finished_attempt = quiz_repository.get_attempt(
        db_path=db_path,
        attempt_id=attempt_id,
    )

    if finished_attempt is None:
        await callback.message.answer(
            "🏁 Тест завершён!",
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    stats = quiz_repository.get_course_quiz_stats(
        db_path=db_path,
        telegram_id=callback.from_user.id,
        course_slug=course_slug,
    )

    await callback.message.answer(
        _quiz_finish_result_text(finished_attempt, stats),
        reply_markup=keyboard,
    )

    await callback.answer()
