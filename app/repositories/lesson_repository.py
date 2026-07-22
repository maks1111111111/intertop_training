from pathlib import Path
from typing import Optional

from app.database.db import get_connection


class LessonRepository:
    """Отвечает за работу с данными уроков."""

    def save(
        self,
        db_path: Path,
        course_id: int,
        slug: str,
        title: str,
        description: str,
        image_path: Optional[Path],
        narration_path: Optional[Path],
        sort_order: int,
    ) -> int:
        image_path_value = (
            str(image_path)
            if image_path is not None and image_path.is_file()
            else None
        )

        narration_path_value = (
            str(narration_path)
            if narration_path is not None and narration_path.is_file()
            else None
        )

        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO lessons (
                    course_id,
                    slug,
                    title,
                    description,
                    lesson_type,
                    content,
                    media_path,
                    sort_order,
                    status
                )
                VALUES (?, ?, ?, ?, 'content', ?, ?, ?, 'published')
                ON CONFLICT(course_id, slug) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    lesson_type = excluded.lesson_type,
                    content = excluded.content,
                    media_path = excluded.media_path,
                    sort_order = excluded.sort_order,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    course_id,
                    slug,
                    title,
                    description,
                    image_path_value,
                    narration_path_value,
                    sort_order,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM lessons
                WHERE course_id = ?
                  AND slug = ?
                """,
                (
                    course_id,
                    slug,
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    f"Не удалось получить ID урока: {slug}"
                )

            return int(row["id"])