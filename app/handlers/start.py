from pathlib import Path

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.repositories.user_repository import UserRepository
from app.services.scanner import scan_courses

router = Router()
user_repository = UserRepository()

def _courses_keyboard(base_dir: Path) -> InlineKeyboardMarkup:
    courses = scan_courses(base_dir)

    buttons = [
        [
            InlineKeyboardButton(
                text=course.title,
                callback_data=f"course:{course.slug}",
            )
        ]
        for course in courses
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    base_dir: Path,
    db_path: Path,
) -> None:
    user = message.from_user

    if user is not None:
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

    name = user.first_name if user and user.first_name else "коллега"

    await message.answer(
        f"Добро пожаловать, <b>{name}</b>! 👋\n\n"
        "Это пространство обучения Intertop.\n"
        "Выберите курс, чтобы продолжить:",
        reply_markup=_courses_keyboard(base_dir),
    )
