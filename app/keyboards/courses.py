from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def back_to_courses_keyboard() -> InlineKeyboardMarkup:
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