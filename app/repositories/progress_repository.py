from typing import Optional, Tuple
from pathlib import Path

from app.database.db import get_connection


class ProgressRepository:
    """Сохраняет и восстанавливает прогресс пользователя."""

    def start_course(
        self,
        db_path: Path,
        telegram_id: int,
        course_slug: str,
    ) -> None:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO enrollments (
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    started_at
                )
                SELECT
                    users.id,
                    courses.id,
                    'in_progress',
                    0,
                    CURRENT_TIMESTAMP
                FROM users
                JOIN courses ON courses.slug = ?
                WHERE users.telegram_id = ?
                ON CONFLICT(user_id, course_id) DO UPDATE SET
                    status = CASE
                        WHEN enrollments.status = 'completed'
                            THEN enrollments.status
                        ELSE 'in_progress'
                    END,
                    started_at = COALESCE(
                        enrollments.started_at,
                        CURRENT_TIMESTAMP
                    )
                """,
                (
                    course_slug,
                    telegram_id,
                ),
            )

    def get_resume_lesson_index(
        self,
        db_path: Path,
        telegram_id: int,
        course_slug: str,
    ) -> int:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS completed_count
                FROM lesson_progress
                JOIN users
                    ON users.id = lesson_progress.user_id
                JOIN lessons
                    ON lessons.id = lesson_progress.lesson_id
                JOIN courses
                    ON courses.id = lessons.course_id
                WHERE users.telegram_id = ?
                  AND courses.slug = ?
                  AND lesson_progress.status = 'completed'
                """,
                (
                    telegram_id,
                    course_slug,
                ),
            ).fetchone()

            if row is None:
                return 0

            return int(row["completed_count"])

    def complete_lesson(
        self,
        db_path: Path,
        telegram_id: int,
        course_slug: str,
        lesson_slug: str,
    ) -> None:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO lesson_progress (
                    user_id,
                    lesson_id,
                    status,
                    started_at,
                    completed_at
                )
                SELECT
                    users.id,
                    lessons.id,
                    'completed',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                FROM users
                JOIN courses
                    ON courses.slug = ?
                JOIN lessons
                    ON lessons.course_id = courses.id
                   AND lessons.slug = ?
                WHERE users.telegram_id = ?
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                    status = 'completed',
                    started_at = COALESCE(
                        lesson_progress.started_at,
                        CURRENT_TIMESTAMP
                    ),
                    completed_at = CURRENT_TIMESTAMP
                """,
                (
                    course_slug,
                    lesson_slug,
                    telegram_id,
                ),
            )

            totals = connection.execute(
                """
                SELECT
                    courses.id AS course_id,
                    users.id AS user_id,
                    COUNT(lessons.id) AS total_lessons,
                    SUM(
                        CASE
                            WHEN lesson_progress.status = 'completed'
                                THEN 1
                            ELSE 0
                        END
                    ) AS completed_lessons
                FROM courses
                JOIN lessons
                    ON lessons.course_id = courses.id
                JOIN users
                    ON users.telegram_id = ?
                LEFT JOIN lesson_progress
                    ON lesson_progress.lesson_id = lessons.id
                   AND lesson_progress.user_id = users.id
                WHERE courses.slug = ?
                GROUP BY courses.id, users.id
                """,
                (
                    telegram_id,
                    course_slug,
                ),
            ).fetchone()

            if totals is None or totals["total_lessons"] == 0:
                return

            progress_percent = round(
                int(totals["completed_lessons"])
                * 100
                / int(totals["total_lessons"])
            )

            connection.execute(
                """
                UPDATE enrollments
                SET progress_percent = ?
                WHERE user_id = ?
                  AND course_id = ?
                """,
                (
                    progress_percent,
                    totals["user_id"],
                    totals["course_id"],
                ),
            )

    def complete_course(
        self,
        db_path: Path,
        telegram_id: int,
        course_slug: str,
    ) -> None:
        with get_connection(db_path) as connection:
            connection.execute(
                """
                UPDATE enrollments
                SET status = 'completed',
                    progress_percent = 100,
                    completed_at = CURRENT_TIMESTAMP
                WHERE user_id = (
                    SELECT id
                    FROM users
                    WHERE telegram_id = ?
                )
                  AND course_id = (
                    SELECT id
                    FROM courses
                    WHERE slug = ?
                )
                """,
                (
                    telegram_id,
                    course_slug,
                ),
            )
    
    def get_course_progress(
        self,
        db_path: Path,
        telegram_id: int,
        course_slug: str,
    ) -> Optional[Tuple[str, int]]:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    enrollments.status,
                    enrollments.progress_percent
                FROM enrollments
                JOIN users
                    ON users.id = enrollments.user_id
                JOIN courses
                    ON courses.id = enrollments.course_id
                WHERE users.telegram_id = ?
                  AND courses.slug = ?
                """,
                (
                    telegram_id,
                    course_slug,
                ),
            ).fetchone()

            if row is None:
                return "not_started", 0

            return (
                str(row["status"]),
                int(row["progress_percent"]),
            )

    def assign_course_to_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
        *,
        assigned_by_user_id: Optional[int] = None,
    ) -> bool:
        """Assign a course to a canonical user without starting it."""
        normalized_user_id = _validate_user_id(user_id)
        normalized_assigned_by_user_id = (
            None
            if assigned_by_user_id is None
            else _validate_user_id(assigned_by_user_id)
        )

        with get_connection(db_path) as connection:
            if normalized_assigned_by_user_id is not None:
                assignment_author = connection.execute(
                    """
                    SELECT 1
                    FROM users
                    WHERE id = ?
                    """,
                    (normalized_assigned_by_user_id,),
                ).fetchone()
                if assignment_author is None:
                    return False

            connection.execute(
                """
                INSERT INTO enrollments (
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    assigned_by_user_id,
                    started_at,
                    completed_at
                )
                SELECT
                    ?,
                    courses.id,
                    'assigned',
                    0,
                    ?,
                    NULL,
                    NULL
                FROM courses
                WHERE courses.slug = ?
                  AND EXISTS (
                      SELECT 1
                      FROM users
                      WHERE users.id = ?
                  )
                ON CONFLICT(user_id, course_id) DO NOTHING
                """,
                (
                    normalized_user_id,
                    normalized_assigned_by_user_id,
                    course_slug,
                    normalized_user_id,
                ),
            )

            row = connection.execute(
                """
                SELECT 1
                FROM enrollments
                JOIN courses
                    ON courses.id = enrollments.course_id
                WHERE enrollments.user_id = ?
                  AND courses.slug = ?
                """,
                (
                    normalized_user_id,
                    course_slug,
                ),
            ).fetchone()

        return row is not None

    def get_assigned_courses_for_user(
        self,
        db_path: Path,
        user_id: int,
    ) -> list[Tuple[str, str, str]]:
        """Return courses explicitly assigned and not yet started."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    courses.slug,
                    courses.title,
                    enrollments.assigned_at
                FROM enrollments
                JOIN courses
                    ON courses.id = enrollments.course_id
                WHERE enrollments.user_id = ?
                  AND enrollments.status = 'assigned'
                ORDER BY
                    enrollments.assigned_at ASC,
                    courses.id ASC,
                    courses.title ASC
                """,
                (normalized_user_id,),
            ).fetchall()

        return [
            (
                str(row["slug"]),
                str(row["title"]),
                str(row["assigned_at"]),
            )
            for row in rows
        ]

    def start_course_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
    ) -> None:
        """Start or resume a course for one canonical user id."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO enrollments (
                    user_id,
                    course_id,
                    status,
                    progress_percent,
                    started_at
                )
                SELECT
                    ?,
                    courses.id,
                    'in_progress',
                    0,
                    CURRENT_TIMESTAMP
                FROM courses
                WHERE courses.slug = ?
                  AND EXISTS (
                      SELECT 1
                      FROM users
                      WHERE users.id = ?
                  )
                ON CONFLICT(user_id, course_id) DO UPDATE SET
                    status = CASE
                        WHEN enrollments.status = 'completed'
                            THEN enrollments.status
                        ELSE 'in_progress'
                    END,
                    started_at = COALESCE(
                        enrollments.started_at,
                        CURRENT_TIMESTAMP
                    )
                """,
                (
                    normalized_user_id,
                    course_slug,
                    normalized_user_id,
                ),
            )

    def get_resume_lesson_index_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
    ) -> int:
        """Return completed lesson count for one canonical user id."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS completed_count
                FROM lesson_progress
                JOIN lessons
                    ON lessons.id = lesson_progress.lesson_id
                JOIN courses
                    ON courses.id = lessons.course_id
                WHERE lesson_progress.user_id = ?
                  AND courses.slug = ?
                  AND lesson_progress.status = 'completed'
                """,
                (
                    normalized_user_id,
                    course_slug,
                ),
            ).fetchone()

        if row is None:
            return 0

        return int(row["completed_count"])

    def complete_lesson_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
        lesson_slug: str,
    ) -> None:
        """Complete one lesson for a canonical user id."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO lesson_progress (
                    user_id,
                    lesson_id,
                    status,
                    started_at,
                    completed_at
                )
                SELECT
                    ?,
                    lessons.id,
                    'completed',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                FROM courses
                JOIN lessons
                    ON lessons.course_id = courses.id
                   AND lessons.slug = ?
                WHERE courses.slug = ?
                  AND EXISTS (
                      SELECT 1
                      FROM users
                      WHERE users.id = ?
                  )
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                    status = 'completed',
                    started_at = COALESCE(
                        lesson_progress.started_at,
                        CURRENT_TIMESTAMP
                    ),
                    completed_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized_user_id,
                    lesson_slug,
                    course_slug,
                    normalized_user_id,
                ),
            )

            totals = connection.execute(
                """
                SELECT
                    courses.id AS course_id,
                    COUNT(lessons.id) AS total_lessons,
                    SUM(
                        CASE
                            WHEN lesson_progress.status = 'completed'
                                THEN 1
                            ELSE 0
                        END
                    ) AS completed_lessons
                FROM courses
                JOIN lessons
                    ON lessons.course_id = courses.id
                LEFT JOIN lesson_progress
                    ON lesson_progress.lesson_id = lessons.id
                   AND lesson_progress.user_id = ?
                WHERE courses.slug = ?
                GROUP BY courses.id
                """,
                (
                    normalized_user_id,
                    course_slug,
                ),
            ).fetchone()

            if totals is None or int(totals["total_lessons"]) == 0:
                return

            progress_percent = round(
                int(totals["completed_lessons"])
                * 100
                / int(totals["total_lessons"])
            )

            connection.execute(
                """
                UPDATE enrollments
                SET progress_percent = ?
                WHERE user_id = ?
                  AND course_id = ?
                """,
                (
                    progress_percent,
                    normalized_user_id,
                    totals["course_id"],
                ),
            )

    def complete_course_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
    ) -> None:
        """Mark one canonical user's course enrollment completed."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            connection.execute(
                """
                UPDATE enrollments
                SET status = 'completed',
                    progress_percent = 100,
                    completed_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                  AND course_id = (
                      SELECT id
                      FROM courses
                      WHERE slug = ?
                  )
                """,
                (
                    normalized_user_id,
                    course_slug,
                ),
            )

    def get_course_progress_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
    ) -> Optional[Tuple[str, int]]:
        """Return course progress for one canonical user id."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    enrollments.status,
                    enrollments.progress_percent
                FROM enrollments
                JOIN courses
                    ON courses.id = enrollments.course_id
                WHERE enrollments.user_id = ?
                  AND courses.slug = ?
                """,
                (
                    normalized_user_id,
                    course_slug,
                ),
            ).fetchone()

        if row is None:
            return "not_started", 0

        return (
            str(row["status"]),
            int(row["progress_percent"]),
        )

    def get_latest_in_progress_course_for_user(
        self,
        db_path: Path,
        user_id: int,
    ) -> Optional[Tuple[str, int]]:
        """Return the latest active course for one canonical user id."""
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    courses.slug,
                    enrollments.progress_percent
                FROM enrollments
                JOIN courses
                    ON courses.id = enrollments.course_id
                LEFT JOIN (
                    SELECT
                        lesson_progress.user_id,
                        lessons.course_id,
                        MAX(
                            COALESCE(
                                lesson_progress.completed_at,
                                lesson_progress.started_at
                            )
                        ) AS last_activity_at
                    FROM lesson_progress
                    JOIN lessons
                        ON lessons.id = lesson_progress.lesson_id
                    GROUP BY
                        lesson_progress.user_id,
                        lessons.course_id
                ) AS activity
                    ON activity.user_id = enrollments.user_id
                   AND activity.course_id = enrollments.course_id
                WHERE enrollments.user_id = ?
                  AND enrollments.status = 'in_progress'
                ORDER BY
                    COALESCE(
                        activity.last_activity_at,
                        enrollments.started_at
                    ) DESC,
                    courses.id DESC
                LIMIT 1
                """,
                (normalized_user_id,),
            ).fetchone()

        if row is None:
            return None

        return (
            str(row["slug"]),
            int(row["progress_percent"]),
        )

    def get_latest_in_progress_course(
        self,
        db_path: Path,
        telegram_id: int,
    ) -> Optional[Tuple[str, int]]:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    courses.slug,
                    enrollments.progress_percent
                FROM enrollments
                JOIN users
                    ON users.id = enrollments.user_id
                JOIN courses
                    ON courses.id = enrollments.course_id
                LEFT JOIN (
                    SELECT
                        lesson_progress.user_id,
                        lessons.course_id,
                        MAX(
                            COALESCE(
                                lesson_progress.completed_at,
                                lesson_progress.started_at
                            )
                        ) AS last_activity_at
                    FROM lesson_progress
                    JOIN lessons
                        ON lessons.id = lesson_progress.lesson_id
                    GROUP BY
                        lesson_progress.user_id,
                        lessons.course_id
                ) AS activity
                    ON activity.user_id = enrollments.user_id
                   AND activity.course_id = enrollments.course_id
                WHERE users.telegram_id = ?
                  AND enrollments.status = 'in_progress'
                ORDER BY
                    COALESCE(
                        activity.last_activity_at,
                        enrollments.started_at
                    ) DESC,
                    courses.id DESC
                LIMIT 1
                """,
                (telegram_id,),
            ).fetchone()

            if row is None:
                return None

            return (
                str(row["slug"]),
                int(row["progress_percent"]),
            )


def _validate_user_id(user_id: int) -> int:
    """Validate a canonical database user id."""
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id
