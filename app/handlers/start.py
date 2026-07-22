from pathlib import Path

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.repositories.progress_repository import ProgressRepository
from app.repositories.user_repository import UserRepository
from app.services.scanner import scan_courses


router = Router()
user_repository = UserRepository()
progress_repository = ProgressRepository()


def _courses_keyboard(
    base_dir: Path,
    db_path: Path,
    telegram_id: int,
) -> InlineKeyboardMarkup:
    courses = scan_courses(base_dir)
    buttons: list[list[InlineKeyboardButton]] = []

    for course in courses:
        status, progress_percent = progress_repository.get_course_progress(
            db_path=db_path,
            telegram_id=telegram_id,
            course_slug=course.slug,
        )

        if status == "completed":
            label = f"✅ {course.title}"
        elif status == "in_progress":
            label = f"🟡 {course.title} — {progress_percent}%"
        else:
            label = f"⚪ {course.title}"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"course:{course.slug}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    base_dir: Path,
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

    courses = scan_courses(base_dir)

    if not courses:
        await message.answer(
            "Добро пожаловать в Intertop Training!\n\n"
            "Курсы пока не опубликованы."
        )
        return

    name = user.first_name or "коллега"

    await message.answer(
        f"Добро пожаловать, <b>{name}</b>! 👋\n\n"
        "Это пространство обучения Intertop.\n"
        "Выберите курс, чтобы продолжить:",
        parse_mode="HTML",
        reply_markup=_courses_keyboard(
            base_dir=base_dir,
            db_path=db_path,
            telegram_id=user.id,
        ),
    )