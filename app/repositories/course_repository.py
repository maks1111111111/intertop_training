import sqlite3
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


class CourseRepository:
    """Отвечает за работу с данными курсов."""

    def get_all(
        self,
        db_path: Path,
    ):
        with get_connection(db_path) as connection:
            return connection.execute(
                """
                SELECT *
                FROM courses
                ORDER BY sort_order, title
                """
            ).fetchall()

    def get_by_slug(
        self,
        db_path: Path,
        slug: str,
    ) -> Optional[sqlite3.Row]:
        with get_connection(db_path) as connection:
            return connection.execute(
                """
                SELECT *
                FROM courses
                WHERE slug = ?
                """,
                (slug,),
            ).fetchone()

    def save(
        self,
        db_path: Path,
        slug: str,
        title: str,
        cover_path: Optional[Path],
        sort_order: int,
    ) -> int:
        cover_path_value = (
            str(cover_path)
            if cover_path is not None
            else None
        )

        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO courses (
                    slug,
                    title,
                    cover_path,
                    sort_order,
                    status
                )
                VALUES (?, ?, ?, ?, 'published')
                ON CONFLICT(slug) DO UPDATE SET
                    title = excluded.title,
                    cover_path = excluded.cover_path,
                    sort_order = excluded.sort_order,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    slug,
                    title,
                    cover_path_value,
                    sort_order,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM courses
                WHERE slug = ?
                """,
                (slug,),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    f"Не удалось получить ID курса: {slug}"
                )

            return int(row["id"])

    _LIFECYCLE_STATUSES = frozenset({"published", "archived"})

    def set_status(
        self,
        db_path: Path,
        slug: str,
        status: str,
    ) -> bool:
        """Update one course lifecycle status. Returns False when the row is missing."""
        normalized_slug = str(slug or "").strip()
        normalized_status = str(status or "").strip().lower()
        if not normalized_slug:
            raise ValueError("Course slug is required.")
        if normalized_status not in self._LIFECYCLE_STATUSES:
            raise ValueError(
                f"Unsupported course status: {status!r}. "
                f"Allowed values: {', '.join(sorted(self._LIFECYCLE_STATUSES))}."
            )

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE courses
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = ?
                """,
                (normalized_status, normalized_slug),
            )
            return cursor.rowcount > 0

    def count_active_enrollments(
        self,
        db_path: Path,
        slug: str,
    ) -> int:
        """Return enrollments with active assignment or in-progress status."""
        normalized_slug = str(slug or "").strip()
        if not normalized_slug:
            return 0

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM enrollments
                INNER JOIN courses ON courses.id = enrollments.course_id
                WHERE courses.slug = ?
                  AND enrollments.status IN ('assigned', 'in_progress')
                """,
                (normalized_slug,),
            ).fetchone()

        return int(row["count"]) if row is not None else 0

    def delete_by_slug(
        self,
        db_path: Path,
        slug: str,
    ) -> bool:
        """Delete one course row by slug. Returns True when a row was removed."""
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM courses
                WHERE slug = ?
                """,
                (slug,),
            )
            return cursor.rowcount > 0