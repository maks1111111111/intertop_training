import sqlite3
from pathlib import Path
from typing import Optional

from app.database.db import get_connection

LEGACY_COMPANY_ID = "intertop"


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("company_id must be a non-empty string")
    return company_id.strip()


class CourseRepository:
    """Отвечает за работу с данными курсов."""

    def get_all(
        self,
        db_path: Path,
        company_id: str = LEGACY_COMPANY_ID,
    ):
        company_id = _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            return connection.execute(
                """
                SELECT *
                FROM courses
                WHERE company_id = ?
                ORDER BY sort_order, title
                """,
                (company_id,),
            ).fetchall()

    def get_by_slug(
        self,
        db_path: Path,
        slug: str,
        company_id: str = LEGACY_COMPANY_ID,
    ) -> Optional[sqlite3.Row]:
        company_id = _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            return connection.execute(
                """
                SELECT *
                FROM courses
                WHERE company_id = ? AND slug = ?
                """,
                (company_id, slug),
            ).fetchone()

    def save(
        self,
        db_path: Path,
        slug: str,
        title: str,
        cover_path: Optional[Path],
        sort_order: int,
        company_id: str = LEGACY_COMPANY_ID,
    ) -> int:
        company_id = _validate_company_id(company_id)
        cover_path_value = (
            str(cover_path)
            if cover_path is not None
            else None
        )

        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO courses (
                    company_id,
                    slug,
                    title,
                    cover_path,
                    sort_order,
                    status
                )
                VALUES (?, ?, ?, ?, ?, 'published')
                ON CONFLICT(company_id, slug) DO UPDATE SET
                    title = excluded.title,
                    cover_path = excluded.cover_path,
                    sort_order = excluded.sort_order,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    company_id,
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
                WHERE company_id = ? AND slug = ?
                """,
                (company_id, slug),
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
        company_id: str = LEGACY_COMPANY_ID,
    ) -> bool:
        """Update one course lifecycle status. Returns False when the row is missing."""
        normalized_slug = str(slug or "").strip()
        company_id = _validate_company_id(company_id)
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
                WHERE company_id = ? AND slug = ?
                """,
                (normalized_status, company_id, normalized_slug),
            )
            return cursor.rowcount > 0

    def count_active_enrollments(
        self,
        db_path: Path,
        slug: str,
        company_id: str = LEGACY_COMPANY_ID,
    ) -> int:
        """Return enrollments with active assignment or in-progress status."""
        normalized_slug = str(slug or "").strip()
        company_id = _validate_company_id(company_id)
        if not normalized_slug:
            return 0

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM enrollments
                INNER JOIN courses ON courses.id = enrollments.course_id
                WHERE courses.company_id = ? AND courses.slug = ?
                  AND enrollments.status IN ('assigned', 'in_progress')
                """,
                (company_id, normalized_slug),
            ).fetchone()

        return int(row["count"]) if row is not None else 0

    def delete_by_slug(
        self,
        db_path: Path,
        slug: str,
        company_id: str = LEGACY_COMPANY_ID,
    ) -> bool:
        """Delete one course row by slug. Returns True when a row was removed."""
        company_id = _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM courses
                WHERE company_id = ? AND slug = ?
                """,
                (company_id, slug),
            )
            return cursor.rowcount > 0
