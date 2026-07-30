from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.content.runtime import ContentRuntime
from app.repositories.progress_repository import ProgressRepository
from app.repositories.user_repository import UserRepository


router = Router()
user_repository = UserRepository()
progress_repository = ProgressRepository()


def _course_button_label(
    title: str,
    status: str,
    progress_percent: int,
) -> str:
    progress_percent = max(0, min(progress_percent, 100))

    if status == "completed":
        return f"✅ {title} · Пройден"

    if status == "in_progress":
        return f"🟡 {title} · {progress_percent}%"

    return f"⚪ {title} · Не начат"


def _courses_keyboard(
    content_runtime: ContentRuntime,
    db_path: Path,
    telegram_id: int,
) -> InlineKeyboardMarkup:
    courses = content_runtime.get_courses()
    buttons: list[list[InlineKeyboardButton]] = []

    for course in courses:
        status, progress_percent = progress_repository.get_course_progress(
            db_path=db_path,
            telegram_id=telegram_id,
            course_slug=course.slug,
        )

        label = _course_button_label(
            title=course.title,
            status=status,
            progress_percent=progress_percent,
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"course_card:{course.slug}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="← Главная",
                callback_data="home:open",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_home_screen(
    content_runtime: ContentRuntime,
    db_path: Path,
    telegram_id: int,
    name: str,
) -> tuple[str, InlineKeyboardMarkup]:
    courses = content_runtime.get_courses()

    active_course = progress_repository.get_latest_in_progress_course(
        db_path=db_path,
        telegram_id=telegram_id,
    )

    if active_course is not None:
        course_slug, progress_percent = active_course
        course = next(
            (
                item
                for item in courses
                if item.slug == course_slug
            ),
            None,
        )

        if course is not None:
            text = (
                f"👋 <b>{name}</b>\n\n"
                "<b>Продолжите обучение</b>\n\n"
                f"{course.title}\n"
                f"Прогресс: <b>{progress_percent}%</b>"
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="▶ Продолжить",
                            callback_data=f"course_start:{course.slug}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📚 Все курсы",
                            callback_data="courses:list",
                        )
                    ],
                ]
            )

            return text, keyboard

    completed_courses = 0

    for course in courses:
        status, _ = progress_repository.get_course_progress(
            db_path=db_path,
            telegram_id=telegram_id,
            course_slug=course.slug,
        )

        if status == "completed":
            completed_courses += 1

    if completed_courses == len(courses):
        text = (
            f"👋 <b>{name}</b>\n\n"
            "<b>Все курсы завершены</b>\n\n"
            "Отличная работа."
        )
    else:
        text = (
            f"👋 <b>{name}</b>\n\n"
            "<b>Intertop Training</b>\n\n"
            "Выберите курс и начните обучение."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📚 Все курсы",
                    callback_data="courses:list",
                )
            ]
        ]
    )

    return text, keyboard


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    user = message.from_user

    if user is None:
        await message.answer(
            "Не удалось определить пользователя Telegram."
        )
        return

    user_repository.save_telegram_user(
        db_path=db_path,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    courses = content_runtime.get_courses()

    if not courses:
        await message.answer(
            "<b>Intertop Training</b>\n\n"
            "Курсы пока не опубликованы.",
            parse_mode="HTML",
        )
        return

    name = user.first_name or "коллега"

    text, keyboard = _build_home_screen(
        content_runtime=content_runtime,
        db_path=db_path,
        telegram_id=user.id,
        name=name,
    )

    await message.answer(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "courses:list")
async def show_courses(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    user = callback.from_user

    if callback.message is None:
        await callback.answer()
        return

    await callback.message.edit_text(
        text="<b>Все курсы</b>\n\nВыберите курс.",
        parse_mode="HTML",
        reply_markup=_courses_keyboard(
            content_runtime=content_runtime,
            db_path=db_path,
            telegram_id=user.id,
        ),
    )

    await callback.answer()


@router.callback_query(F.data == "home:open")
async def show_home(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    user = callback.from_user

    if callback.message is None:
        await callback.answer()
        return

    name = user.first_name or "коллега"

    text, keyboard = _build_home_screen(
        content_runtime=content_runtime,
        db_path=db_path,
        telegram_id=user.id,
        name=name,
    )

    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    await callback.answer()
