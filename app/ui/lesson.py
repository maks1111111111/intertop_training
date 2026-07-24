from html import escape

from app.services.scanner import Course, Lesson
from app.ui.theme import DIVIDER
from app.ui.widgets import progress_bar

def lesson_header(
    course: Course,
    lesson: Lesson,
    lesson_number: int,
    lessons_count: int,
) -> str:
    progress_percent = (
        round(lesson_number / lessons_count * 100)
        if lessons_count
        else 0
    )

    return (
        f"📚 <b>{escape(course.title)}</b>\n\n"
        f"👟 <b>{escape(lesson.title)}</b>\n\n"
        f"{DIVIDER}\n\n"
        f"📖 Урок {lesson_number} из {lessons_count}\n"
        f"{progress_bar(lesson_number, lessons_count)}  {progress_percent}%"
    )

def lesson_view_text(
    course: Course,
    lesson: Lesson,
    lesson_index: int,
) -> str:
    lesson_number = lesson_index + 1
    lessons_count = len(course.lessons)

    return lesson_header(
        course=course,
        lesson=lesson,
        lesson_number=lesson_number,
        lessons_count=lessons_count,
    )

    