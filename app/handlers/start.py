from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.scanner import scan_courses

router = Router()


def _courses_keyboard(base_dir) -> InlineKeyboardMarkup:
    courses = scan_courses(base_dir)
    buttons = [
        [InlineKeyboardButton(text=course.title, callback_data=f"course:{course.slug}")]
        for course in courses
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message, base_dir) -> None:
    courses = scan_courses(base_dir)

    if not courses:
        await message.answer(
            "Добро пожаловать в обучение Intertop!\n\n"
            "Курсы пока не найдены. Добавьте папки с уроками в каталог courses/."
        )
        return

    await message.answer(
        "Добро пожаловать в обучение Intertop!\n\n"
        "Выберите курс:",
        reply_markup=_courses_keyboard(base_dir),
    )
