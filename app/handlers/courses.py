from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app.services.scanner import get_course

router = Router()


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← К списку курсов", callback_data="courses:list")]
        ]
    )


async def _send_lesson(callback: CallbackQuery, lesson_path: Path) -> None:
    file = FSInputFile(lesson_path)
    suffix = lesson_path.suffix.lower()

    if suffix == ".mp3":
        await callback.message.answer_audio(audio=file)
    elif suffix == ".mp4":
        await callback.message.answer_video(video=file)
    else:
        await callback.message.answer_document(document=file)


@router.callback_query(F.data == "courses:list")
async def show_courses_list(callback: CallbackQuery, base_dir) -> None:
    from app.handlers.start import _courses_keyboard

    await callback.message.edit_text(
        "Выберите курс:",
        reply_markup=_courses_keyboard(base_dir),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("course:"))
async def show_course(callback: CallbackQuery, base_dir) -> None:
    slug = callback.data.removeprefix("course:")
    course = get_course(base_dir, slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    await callback.answer()

    if course.cover_path:
        await callback.message.answer_photo(
            photo=FSInputFile(course.cover_path),
            caption=f"📚 {course.title}",
        )
    else:
        await callback.message.answer(f"📚 {course.title}")

    if not course.lessons:
        await callback.message.answer(
            "В этом курсе пока нет уроков.\n"
            "Добавьте файлы .mp3 или .mp4 с префиксом номера, например: 01_введение.mp3",
            reply_markup=_back_keyboard(),
        )
        return

    for index, lesson in enumerate(course.lessons, start=1):
        await callback.message.answer(f"Урок {index}: {lesson.title}")
        await _send_lesson(callback, lesson.path)

    await callback.message.answer(
        f"Курс «{course.title}» завершён.",
        reply_markup=_back_keyboard(),
    )
