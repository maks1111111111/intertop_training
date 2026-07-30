from pathlib import Path

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from app.content.runtime import ContentRuntime
from app.keyboards.courses import back_to_courses_keyboard
from app.ui.lesson import lesson_view_text
from app.repositories.progress_repository import ProgressRepository
from app.services.scanner import Course, Lesson


router = Router()
progress_repository = ProgressRepository()


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
    if callback.message is None:
        await callback.answer()
        return

    lessons_count = len(course.lessons)

    await callback.message.answer(
        lesson_view_text(
            course=course,
            lesson=lesson,
            lesson_index=lesson_index,
        ),
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
        "Выберите действие:",
        reply_markup=_lesson_keyboard(
            course_slug=course.slug,
            lesson_index=lesson_index,
            lessons_count=lessons_count,
        ),
    )


@router.callback_query(F.data.startswith("course_card:"))
async def show_course_card(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    course_slug = callback.data.removeprefix("course_card:")
    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    status, progress_percent = progress_repository.get_course_progress(
        db_path=db_path,
        telegram_id=callback.from_user.id,
        course_slug=course_slug,
    )

    lessons_count = len(course.lessons)

    if status == "completed":
        status_text = "✅ Завершён"
    elif status == "in_progress":
        status_text = f"🟡 В процессе · {progress_percent}%"
    else:
        status_text = "⚪ Не начат"

    if not course.lessons:
        text = (
            f"<b>{course.title}</b>\n\n"
            "Курс готовится к публикации.\n"
            "Материалы появятся позже."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="← К курсам",
                        callback_data="courses:list",
                    )
                ]
            ]
        )
    else:
        text = (
            f"<b>{course.title}</b>\n\n"
            f"Уроков: {lessons_count}\n"
            f"Статус: {status_text}"
        )

        if status == "completed":
            main_button_text = "📖 Открыть"
        elif status == "in_progress":
            main_button_text = "▶ Продолжить"
        else:
            main_button_text = "▶ Начать"

        buttons: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text=main_button_text,
                    callback_data=f"course_start:{course_slug}",
                )
            ],
        ]

        if status == "completed" and course.quiz is not None:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="📝 Пройти тест",
                        callback_data=f"quiz_start:{course_slug}",
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    text="← К курсам",
                    callback_data="courses:list",
                )
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if callback.message is None:
        await callback.answer()
        return

    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    await callback.answer()


@router.callback_query(F.data.startswith("course_start:"))
async def start_course(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    course_slug = callback.data.removeprefix("course_start:")
    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer("Курс не найден.", show_alert=True)
        return

    if not course.lessons:
        await callback.answer()

        await callback.message.answer(
            "В этом курсе пока нет уроков.",
            reply_markup=back_to_courses_keyboard(),
        )
        return

    user = callback.from_user

    progress_repository.start_course(
        db_path=db_path,
        telegram_id=user.id,
        course_slug=course_slug,
    )

    lesson_index = progress_repository.get_resume_lesson_index(
        db_path=db_path,
        telegram_id=user.id,
        course_slug=course_slug,
    )

    if lesson_index >= len(course.lessons):
        lesson_index = len(course.lessons) - 1

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
        lesson=course.lessons[lesson_index],
        lesson_index=lesson_index,
    )


@router.callback_query(F.data.startswith("lesson:"))
async def show_lesson(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "Некорректная команда.",
            show_alert=True,
        )
        return

    _, course_slug, lesson_index_raw = parts

    try:
        lesson_index = int(lesson_index_raw)
    except ValueError:
        await callback.answer(
            "Некорректный номер урока.",
            show_alert=True,
        )
        return

    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer(
            "Курс не найден.",
            show_alert=True,
        )
        return

    if lesson_index < 0 or lesson_index >= len(course.lessons):
        await callback.answer(
            "Урок не найден.",
            show_alert=True,
        )
        return

    previous_lesson_index = lesson_index - 1

    if previous_lesson_index >= 0:
        previous_lesson = course.lessons[previous_lesson_index]

        progress_repository.complete_lesson(
            db_path=db_path,
            telegram_id=callback.from_user.id,
            course_slug=course_slug,
            lesson_slug=previous_lesson.path.name,
        )

    await callback.answer()

    await _send_lesson(
        callback=callback,
        course=course,
        lesson=course.lessons[lesson_index],
        lesson_index=lesson_index,
    )


@router.callback_query(F.data.startswith("course_complete:"))
async def complete_course(
    callback: CallbackQuery,
    content_runtime: ContentRuntime,
    db_path: Path,
) -> None:
    course_slug = callback.data.removeprefix("course_complete:")
    course = content_runtime.get_course(course_slug)

    if course is None:
        await callback.answer(
            "Курс не найден.",
            show_alert=True,
        )
        return

    if course.lessons:
        last_lesson = course.lessons[-1]

        progress_repository.complete_lesson(
            db_path=db_path,
            telegram_id=callback.from_user.id,
            course_slug=course_slug,
            lesson_slug=last_lesson.path.name,
        )

    progress_repository.complete_course(
        db_path=db_path,
        telegram_id=callback.from_user.id,
        course_slug=course_slug,
    )

    await callback.answer("Курс завершён!")

    if callback.message is None:
        return

    congratulation_text = (
        f"🎉 Поздравляем!\n\n"
        f"Вы успешно завершили курс «{course.title}»."
    )

    if course.quiz is not None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📝 Пройти тест",
                        callback_data=f"quiz_start:{course_slug}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="← К списку курсов",
                        callback_data="courses:list",
                    )
                ],
            ]
        )
    else:
        keyboard = back_to_courses_keyboard()

    await callback.message.answer(
        congratulation_text,
        reply_markup=keyboard,
    )
