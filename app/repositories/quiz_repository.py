import sqlite3
from pathlib import Path
from typing import Optional

from app.database.db import get_connection

DEFAULT_PASSING_SCORE = 80


def create_attempt(
    db_path: Path,
    telegram_id: int,
    course_slug: str,
    quiz_version: int,
    questions_count: int,
) -> Optional[int]:
    with get_connection(db_path) as connection:
        active_attempt = connection.execute(
            """
            SELECT quiz_attempts.id
            FROM quiz_attempts
            JOIN users
                ON users.id = quiz_attempts.user_id
            WHERE users.telegram_id = ?
              AND quiz_attempts.course_slug = ?
              AND quiz_attempts.finished_at IS NULL
            ORDER BY quiz_attempts.started_at DESC
            LIMIT 1
            """,
            (
                telegram_id,
                course_slug,
            ),
        ).fetchone()

        if active_attempt is not None:
            return int(active_attempt["id"])

        cursor = connection.execute(
            """
            INSERT INTO quiz_attempts (
                user_id,
                course_slug,
                quiz_version,
                started_at,
                questions_count
            )
            SELECT
                users.id,
                ?,
                ?,
                CURRENT_TIMESTAMP,
                ?
            FROM users
            WHERE users.telegram_id = ?
            """,
            (
                course_slug,
                quiz_version,
                questions_count,
                telegram_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

        return int(cursor.lastrowid)


def save_answer(
    db_path: Path,
    attempt_id: int,
    question_id: str,
    selected_option_id: str,
    is_correct: bool,
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO quiz_answers (
                attempt_id,
                question_id,
                selected_option_id,
                is_correct
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                attempt_id,
                question_id,
                selected_option_id,
                int(is_correct),
            ),
        )


def finish_attempt(
    db_path: Path,
    attempt_id: int,
    passing_score: int = DEFAULT_PASSING_SCORE,
) -> None:
    with get_connection(db_path) as connection:
        attempt = connection.execute(
            """
            SELECT questions_count
            FROM quiz_attempts
            WHERE id = ?
              AND finished_at IS NULL
            """,
            (attempt_id,),
        ).fetchone()

        if attempt is None:
            return

        questions_count = int(attempt["questions_count"])
        if questions_count == 0:
            return

        stats = connection.execute(
            """
            SELECT
                COUNT(*) AS answered_count,
                COALESCE(SUM(is_correct), 0) AS correct_answers
            FROM quiz_answers
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()

        correct_answers = int(stats["correct_answers"])
        score_percent = round(
            correct_answers * 100 / questions_count,
            2,
        )
        passed = int(score_percent >= passing_score)

        connection.execute(
            """
            UPDATE quiz_attempts
            SET finished_at = CURRENT_TIMESTAMP,
                correct_answers = ?,
                score_percent = ?,
                passed = ?
            WHERE id = ?
            """,
            (
                correct_answers,
                score_percent,
                passed,
                attempt_id,
            ),
        )


def get_attempt(
    db_path: Path,
    attempt_id: int,
) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM quiz_attempts
            WHERE id = ?
            """,
            (attempt_id,),
        ).fetchone()


def get_active_attempt(
    db_path: Path,
    telegram_id: int,
    course_slug: str,
) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT quiz_attempts.*
            FROM quiz_attempts
            JOIN users
                ON users.id = quiz_attempts.user_id
            WHERE users.telegram_id = ?
              AND quiz_attempts.course_slug = ?
              AND quiz_attempts.finished_at IS NULL
            ORDER BY quiz_attempts.started_at DESC
            LIMIT 1
            """,
            (
                telegram_id,
                course_slug,
            ),
        ).fetchone()
