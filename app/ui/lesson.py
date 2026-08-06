from html import escape

from app.content.practical_task import PracticalTask
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


def _format_bullet_section(title: str, items: tuple[str, ...]) -> str:
    lines = [title]
    lines.extend(f"• {escape(item)}" for item in items)
    return "\n".join(lines)


def _format_structured_practical_task(task: PracticalTask) -> str:
    lines = [
        "🛠 Практическое задание",
        "",
        f"<b>{escape(task.title)}</b>",
        "",
        escape(task.description),
        "",
        f"🎯 Ожидаемый результат:\n{escape(task.expected_result)}",
    ]
    if task.estimated_minutes is not None:
        lines.extend(
            [
                "",
                f"⏱ Ориентировочное время: {task.estimated_minutes} мин.",
            ]
        )
    return "\n".join(lines)


def lesson_quality_sections_text(lesson: Lesson) -> str:
    """Return optional lesson quality blocks for Telegram HTML messages."""
    sections: list[str] = []

    if lesson.structured_practical_task is not None:
        sections.append(
            _format_structured_practical_task(lesson.structured_practical_task),
        )
    else:
        practical_task = lesson.practical_task.strip()
        if practical_task:
            sections.append(
                f"🛠 Практическое задание\n{escape(practical_task)}",
            )

    if lesson.checklist:
        sections.append(
            _format_bullet_section("✅ Чек-лист", lesson.checklist),
        )

    if lesson.common_mistakes:
        sections.append(
            _format_bullet_section("⚠ Типичные ошибки", lesson.common_mistakes),
        )

    if lesson.key_takeaways:
        sections.append(
            _format_bullet_section("💡 Главное запомнить", lesson.key_takeaways),
        )

    if lesson.application_tips:
        sections.append(
            _format_bullet_section("🚀 Советы по применению", lesson.application_tips),
        )

    return "\n\n".join(sections)


def lesson_body_text(lesson: Lesson) -> str:
    """Return lesson description followed by optional quality sections."""
    parts: list[str] = []

    if lesson.description:
        parts.append(lesson.description)

    quality_sections = lesson_quality_sections_text(lesson)
    if quality_sections:
        parts.append(quality_sections)

    return "\n\n".join(parts)


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
