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