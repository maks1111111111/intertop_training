"""Admin course preview context without learner progress side effects."""

from __future__ import annotations

from dataclasses import dataclass

from app.web.progress_service import CourseProgressView, LessonProgressRow


@dataclass(frozen=True)
class PreviewContext:
    """Template context for admin course preview mode."""

    slug: str
    admin_url: str
    base_url: str

    @classmethod
    def for_course(cls, slug: str) -> PreviewContext:
        """Build preview URLs for one course slug."""
        return cls(
            slug=slug,
            admin_url=f"/admin/courses/{slug}",
            base_url=f"/admin/courses/{slug}/preview",
        )

    def lesson_url(self, lesson_id: str) -> str:
        """Return the preview URL for one lesson."""
        return f"{self.base_url}/lessons/{lesson_id}"

    @property
    def quiz_url(self) -> str:
        """Return the preview URL for the course quiz."""
        return f"{self.base_url}/quiz"


def build_preview_progress_view(
    lessons: tuple,
    *,
    has_quiz: bool,
) -> CourseProgressView:
    """Build a read-only progress view where every lesson stays accessible."""
    lesson_rows: list[LessonProgressRow] = []
    for lesson in lessons:
        lesson_rows.append(
            LessonProgressRow(
                id=lesson.id,
                title=lesson.title,
                order=lesson.order,
                status="preview",
                status_label="Доступен",
            )
        )

    completion_message = None
    if has_quiz and lesson_rows:
        completion_message = "После просмотра уроков можно пройти итоговый тест"

    return CourseProgressView(
        percent=0,
        completed_count=0,
        total_count=len(lesson_rows),
        is_completed=False,
        completion_message=completion_message,
        lesson_rows=tuple(lesson_rows),
    )
