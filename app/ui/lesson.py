from html import escape

from app.services.scanner import Course, Lesson


def progress_bar(
    current: int,
    total: int,
    length: int = 10,
) -> str:
    if total <= 0:
        return "░" * length

    filled = round(current / total * length)
    filled = max(0, min(filled, length))

    return "█" * filled + "░" * (length - filled)


def lesson_view_text(
    course: Course,
    lesson: Lesson,
    lesson_index: int,
) -> str:
    lesson_number = lesson_index + 1
    lessons_count = len(course.lessons)

    if lessons_count <= 0:
        progress_percent = 0
    else:
        progress_percent = round(lesson_number / lessons_count * 100)

    return (
        f"📚 <b>{escape(course.title)}</b>\n\n"
        f"📖 Урок {lesson_number} из {lessons_count}\n"
        f"{progress_bar(lesson_number, lessons_count)} {progress_percent}%\n\n"
        f"<b>{escape(lesson.title)}</b>"
    )