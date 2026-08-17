import sqlite3
from pathlib import Path
from typing import Optional, TypedDict

from app.database.db import get_connection

DEFAULT_PASSING_SCORE = 80

_USER_COURSE_ATTEMPTS_FROM = """
    FROM quiz_attempts
    JOIN users
        ON users.id = quiz_attempts.user_id
    WHERE users.telegram_id = ?
      AND quiz_attempts.course_slug = ?
"""


class CourseQuizStats(TypedDict):
    attempts_count: int
    best_score_percent: Optional[float]
    average_score_percent: Optional[float]
    latest_score_percent: Optional[float]
    latest_finished_at: Optional[str]
    latest_passed: bool
    ever_passed: bool


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
) -> bool:
    """Persist one answer for a question within an attempt.

    Returns ``True`` when the answer is stored for the first time.
    Returns ``False`` when the question was already answered in this attempt.
    """
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO quiz_answers (
                attempt_id,
                question_id,
                selected_option_id,
                is_correct
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(attempt_id, question_id) DO NOTHING
            """,
            (
                attempt_id,
                question_id,
                selected_option_id,
                int(is_correct),
            ),
        )
        return cursor.rowcount == 1


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
        if correct_answers > questions_count:
            correct_answers = questions_count
        score_percent = round(
            correct_answers * 100 / questions_count,
            2,
        )
        if score_percent > 100.0:
            score_percent = 100.0
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
            f"""
            SELECT quiz_attempts.*
            {_USER_COURSE_ATTEMPTS_FROM}
              AND quiz_attempts.finished_at IS NULL
            ORDER BY quiz_attempts.started_at DESC
            LIMIT 1
            """,
            (
                telegram_id,
                course_slug,
            ),
        ).fetchone()


def get_finished_attempts(
    db_path: Path,
    telegram_id: int,
    course_slug: str,
    limit: int = 10,
) -> list[sqlite3.Row]:
    if limit <= 0:
        return []

    with get_connection(db_path) as connection:
        return connection.execute(
            f"""
            SELECT quiz_attempts.*
            {_USER_COURSE_ATTEMPTS_FROM}
              AND quiz_attempts.finished_at IS NOT NULL
            ORDER BY quiz_attempts.finished_at DESC, quiz_attempts.id DESC
            LIMIT ?
            """,
            (
                telegram_id,
                course_slug,
                limit,
            ),
        ).fetchall()


def get_course_quiz_stats(
    db_path: Path,
    telegram_id: int,
    course_slug: str,
) -> CourseQuizStats:
    params = (
        telegram_id,
        course_slug,
    )

    with get_connection(db_path) as connection:
        aggregate = connection.execute(
            f"""
            SELECT
                COUNT(*) AS attempts_count,
                MAX(quiz_attempts.score_percent) AS best_score_percent,
                AVG(quiz_attempts.score_percent) AS average_score_percent,
                MAX(quiz_attempts.passed) AS ever_passed
            {_USER_COURSE_ATTEMPTS_FROM}
              AND quiz_attempts.finished_at IS NOT NULL
            """,
            params,
        ).fetchone()

        latest = connection.execute(
            f"""
            SELECT
                quiz_attempts.score_percent,
                quiz_attempts.finished_at,
                quiz_attempts.passed
            {_USER_COURSE_ATTEMPTS_FROM}
              AND quiz_attempts.finished_at IS NOT NULL
            ORDER BY quiz_attempts.finished_at DESC, quiz_attempts.id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    attempts_count = int(aggregate["attempts_count"])

    if attempts_count == 0:
        return CourseQuizStats(
            attempts_count=0,
            best_score_percent=None,
            average_score_percent=None,
            latest_score_percent=None,
            latest_finished_at=None,
            latest_passed=False,
            ever_passed=False,
        )

    return CourseQuizStats(
        attempts_count=attempts_count,
        best_score_percent=float(aggregate["best_score_percent"]),
        average_score_percent=float(aggregate["average_score_percent"]),
        latest_score_percent=float(latest["score_percent"]),
        latest_finished_at=str(latest["finished_at"]),
        latest_passed=bool(latest["passed"]),
        ever_passed=bool(aggregate["ever_passed"]),
    )
def _validate_user_id(user_id: int) -> int:
    """Validate a canonical database user id."""
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def create_attempt_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    quiz_version: int,
    questions_count: int,
) -> Optional[int]:
    """Create or return the active quiz attempt for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)

    with get_connection(db_path) as connection:
        active_attempt = connection.execute(
            """
            SELECT id
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND finished_at IS NULL
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (
                normalized_user_id,
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
            WHERE users.id = ?
            """,
            (
                course_slug,
                quiz_version,
                questions_count,
                normalized_user_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

        return int(cursor.lastrowid)


def get_active_attempt_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
) -> Optional[sqlite3.Row]:
    """Return the active quiz attempt for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND finished_at IS NULL
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (
                normalized_user_id,
                course_slug,
            ),
        ).fetchone()


def get_finished_attempts_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    limit: int = 10,
) -> list[sqlite3.Row]:
    """Return finished quiz attempts for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)

    if limit <= 0:
        return []

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND finished_at IS NOT NULL
            ORDER BY finished_at DESC, id DESC
            LIMIT ?
            """,
            (
                normalized_user_id,
                course_slug,
                limit,
            ),
        ).fetchall()


def get_course_quiz_stats_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
) -> CourseQuizStats:
    """Return quiz statistics for one canonical user and course."""
    normalized_user_id = _validate_user_id(user_id)
    params = (
        normalized_user_id,
        course_slug,
    )

    with get_connection(db_path) as connection:
        aggregate = connection.execute(
            """
            SELECT
                COUNT(*) AS attempts_count,
                MAX(score_percent) AS best_score_percent,
                AVG(score_percent) AS average_score_percent,
                MAX(passed) AS ever_passed
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND finished_at IS NOT NULL
            """,
            params,
        ).fetchone()

        latest = connection.execute(
            """
            SELECT
                score_percent,
                finished_at,
                passed
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND finished_at IS NOT NULL
            ORDER BY finished_at DESC, id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    attempts_count = int(aggregate["attempts_count"])

    if attempts_count == 0:
        return CourseQuizStats(
            attempts_count=0,
            best_score_percent=None,
            average_score_percent=None,
            latest_score_percent=None,
            latest_finished_at=None,
            latest_passed=False,
            ever_passed=False,
        )

    return CourseQuizStats(
        attempts_count=attempts_count,
        best_score_percent=float(aggregate["best_score_percent"]),
        average_score_percent=float(aggregate["average_score_percent"]),
        latest_score_percent=float(latest["score_percent"]),
        latest_finished_at=str(latest["finished_at"]),
        latest_passed=bool(latest["passed"]),
        ever_passed=bool(aggregate["ever_passed"]),
    )
