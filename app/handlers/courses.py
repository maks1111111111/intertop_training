from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.services.scanner import Course, Lesson, get_course

router = Router()


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="← К списку курсов",
                    callback_data="courses:list",
                )
            ]
        ]
    )


def _lesson_keyboard(
    course_slug: str,
    lesson_index: int,
    lessons_count: int,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    navigation: list[InlineKeyboardButton] = []

    if lesson_index > 0:
        navigation.append(
            InlineKeyboardButton(
                text="← Предыдущий",
                callback_data=f"lesson:{course_slug}:{lesson_index - 1}",
            )
        )

    if lesson_index < lessons_count - 1:
        navigation.append(
            InlineKeyboardButton(
                text="Следующий →",
                callback_data=f"lesson:{course_slug}:{lesson_index + 1}",
            )
        )
    else:
        navigation.append(
            InlineKeyboardButton(
                text="✅ Завершить курс",
                callback_data=f"course_complete:{course_slug}",
            )
        )

    buttons.append(navigation)

    buttons.append(
        [
            InlineKeyboardButton(
                text="← К списку курсов",
                callback_data="courses:list",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _send_lesson(
    callback: CallbackQuery,
    course: Course,
    lesson: Lesson,
    lesson_index: int,
) -> None:
    lesson_number = lesson_index + 1
    lessons_count = len(course.lessons)

    await callback.message.answer(
        f"📖 Урок {lesson_number} из {lessons_count}\n"
        f"<b>{lesson.title}</b>",
        parse_mode="HTML",
    )

    if lesson.image_path and lesson.image_path.is_file():
        await callback.message.answer_photo(
            photo=FSInputFile(lesson.image_path),
            caption=lesson.description or None,
        )
    elif lesson.description:
        await callback.message.answer(lesson.description)

    if lesson.narration_path and lesson.narration_path.is_file():
        await callback.message.answer_audio(
            audio=FSInputFile(lesson.narration_path),
        )

    await callback.message.answer(
        f"Урок {lesson_number} из {lessons_count}",
        reply_markup=_lesson_keyboard(
            course_slug=course.slug,
            lesson_index=lesson_index,
            lessons_count=lessons_count,
        ),
    )


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

    if not course.lessons:
        await callback.answer()

        await callback.message.answer(
            "В этом курсе пока нет уроков.",
            reply_markup=_back_keyboard(),
        )
        return

    await callback.answer()

    if course.cover_path and course.cover_path.is_file():
        await callback.message.answer_photo(
            photo=FSInputFile(course.cover_path),
            caption=f"📚 {course.title}",
        )
    else:
        await callback.message.answer(f"📚 {course.title}")

    await _send_lesson(
        callback=callback,
        course=course,
        lesson=course.lessons[0],
        lesson_index=0,
    )


@router.callback_query(F.data.startswith("lesson:"))
async def show_lesson(callback: CallbackQuery, base_dir) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer("Некорректная команда.", show_alert=True)
        return

    _, course_slug, lesson_index_raw = parts

    try:
        lesson_index = int(lesson_index_raw)
    except ValueError:
        await callback.answer("Некорректный номер урока.", show_alert=True)
        return

    course = get_course(base_dir, course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    if lesson_index < 0 or lesson_index >= len(course.lessons):
        await callback.answer("Урок не найден.", show_alert=True)
        return

    await callback.answer()

    await _send_lesson(
        callback=callback,
        course=course,
        lesson=course.lessons[lesson_index],
        lesson_index=lesson_index,
    )


@router.callback_query(F.data.startswith("course_complete:"))
async def complete_course(callback: CallbackQuery, base_dir) -> None:
    course_slug = callback.data.removeprefix("course_complete:")
    course = get_course(base_dir, course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    await callback.answer("Курс завершён!")

    await callback.message.answer(
        f"🎉 Курс «{course.title}» завершён.",
        reply_markup=_back_keyboard(),
    )