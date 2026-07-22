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