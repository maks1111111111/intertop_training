import sqlite3
from pathlib import Path
from typing import Optional, TypedDict

from app.database.db import get_connection

LEGACY_COMPANY_ID = "intertop"

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
    company_id: str = LEGACY_COMPANY_ID,
) -> bool:
    """Persist one answer for a question within an attempt.

    Returns ``True`` when the answer is stored for the first time.
    Returns ``False`` when the question was already answered in this attempt.
    """
    normalized_company_id = _validate_company_id(company_id)

    with get_connection(db_path) as connection:
        company_scoped = _has_company_id_column(connection)
        company_predicate = " AND company_id = ?" if company_scoped else ""
        attempt_params: tuple[object, ...] = (attempt_id,)
        if company_scoped:
            attempt_params += (normalized_company_id,)
        attempt = connection.execute(
            """
            SELECT 1
            FROM quiz_attempts
            WHERE id = ?
            """ + company_predicate,
            attempt_params,
        ).fetchone()
        if attempt is None:
            return False

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
    company_id: str = LEGACY_COMPANY_ID,
) -> bool:
    """Finish an active attempt within its owning company."""
    normalized_company_id = _validate_company_id(company_id)

    with get_connection(db_path) as connection:
        company_scoped = _has_company_id_column(connection)
        company_predicate = " AND company_id = ?" if company_scoped else ""
        attempt_params: tuple[object, ...] = (attempt_id,)
        if company_scoped:
            attempt_params += (normalized_company_id,)
        attempt = connection.execute(
            """
            SELECT questions_count
            FROM quiz_attempts
            WHERE id = ?
              AND finished_at IS NULL
            """ + company_predicate,
            attempt_params,
        ).fetchone()

        if attempt is None:
            return False

        questions_count = int(attempt["questions_count"])
        if questions_count == 0:
            return False

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

        update_params: tuple[object, ...] = (
            correct_answers,
            score_percent,
            passed,
            attempt_id,
        )
        if company_scoped:
            update_params += (normalized_company_id,)
        cursor = connection.execute(
            """
            UPDATE quiz_attempts
            SET finished_at = CURRENT_TIMESTAMP,
                correct_answers = ?,
                score_percent = ?,
                passed = ?
            WHERE id = ?
              AND finished_at IS NULL
            """ + company_predicate,
            update_params,
        )
        return cursor.rowcount == 1


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


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("company_id must be a non-empty string")
    return company_id.strip()


def _has_company_id_column(connection) -> bool:
    """Recognize pre-SaaS quiz fixtures as legacy Intertop-only storage."""
    return any(
        row["name"] == "company_id"
        for row in connection.execute("PRAGMA table_info(quiz_attempts)")
    )


def _has_active_membership(connection, company_id: str, user_id: int) -> bool:
    """Keep legacy Telegram writes compatible while guarding SaaS tenants."""
    if company_id == LEGACY_COMPANY_ID:
        return True
    return connection.execute(
        """
        SELECT 1
        FROM company_memberships
        WHERE company_id = ?
          AND user_id = ?
          AND is_active = 1
        LIMIT 1
        """,
        (company_id, user_id),
    ).fetchone() is not None


def _has_course_for_company(connection, company_id: str, course_slug: str) -> bool:
    """Require a catalog course for SaaS assessment records."""
    if company_id == LEGACY_COMPANY_ID:
        return True
    return connection.execute(
        """
        SELECT 1
        FROM courses
        WHERE company_id = ?
          AND slug = ?
        LIMIT 1
        """,
        (company_id, course_slug),
    ).fetchone() is not None


def create_attempt_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    quiz_version: int,
    questions_count: int,
    company_id: str = LEGACY_COMPANY_ID,
) -> Optional[int]:
    """Create or return the active quiz attempt for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)
    normalized_company_id = _validate_company_id(company_id)

    with get_connection(db_path) as connection:
        if not _has_active_membership(
            connection, normalized_company_id, normalized_user_id
        ):
            return None
        if not _has_course_for_company(
            connection, normalized_company_id, course_slug
        ):
            return None

        active_attempt = connection.execute(
            """
            SELECT id
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND company_id = ?
              AND finished_at IS NULL
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (
                normalized_user_id,
                course_slug,
                normalized_company_id,
            ),
        ).fetchone()

        if active_attempt is not None:
            return int(active_attempt["id"])

        cursor = connection.execute(
            """
            INSERT INTO quiz_attempts (
                company_id,
                user_id,
                course_slug,
                quiz_version,
                started_at,
                questions_count
            )
            SELECT
                ?,
                users.id,
                ?,
                ?,
                CURRENT_TIMESTAMP,
                ?
            FROM users
            WHERE users.id = ?
            """,
            (
                normalized_company_id,
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
    company_id: str = LEGACY_COMPANY_ID,
) -> Optional[sqlite3.Row]:
    """Return the active quiz attempt for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)
    normalized_company_id = _validate_company_id(company_id)

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND company_id = ?
              AND finished_at IS NULL
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (
                normalized_user_id,
                course_slug,
                normalized_company_id,
            ),
        ).fetchone()


def get_finished_attempts_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    limit: int = 10,
    company_id: str = LEGACY_COMPANY_ID,
) -> list[sqlite3.Row]:
    """Return finished quiz attempts for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)
    normalized_company_id = _validate_company_id(company_id)

    if limit <= 0:
        return []

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM quiz_attempts
            WHERE user_id = ?
              AND course_slug = ?
              AND company_id = ?
              AND finished_at IS NOT NULL
            ORDER BY finished_at DESC, id DESC
            LIMIT ?
            """,
            (
                normalized_user_id,
                course_slug,
                normalized_company_id,
                limit,
            ),
        ).fetchall()


def get_finished_answers_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    company_id: str = LEGACY_COMPANY_ID,
) -> list[sqlite3.Row]:
    """Return answers from finished quiz attempts for a canonical user and course."""
    normalized_user_id = _validate_user_id(user_id)
    normalized_company_id = _validate_company_id(company_id)

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT
                quiz_answers.attempt_id,
                quiz_answers.question_id,
                quiz_answers.is_correct,
                quiz_attempts.finished_at
            FROM quiz_answers
            JOIN quiz_attempts
                ON quiz_attempts.id = quiz_answers.attempt_id
            WHERE quiz_attempts.user_id = ?
              AND quiz_attempts.course_slug = ?
              AND quiz_attempts.company_id = ?
              AND quiz_attempts.finished_at IS NOT NULL
            ORDER BY
                quiz_attempts.finished_at ASC,
                quiz_attempts.id ASC,
                quiz_answers.id ASC
            """,
            (
                normalized_user_id,
                course_slug,
                normalized_company_id,
            ),
        ).fetchall()


def get_course_quiz_stats_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    company_id: str = LEGACY_COMPANY_ID,
) -> CourseQuizStats:
    """Return quiz statistics for one canonical user and course."""
    normalized_user_id = _validate_user_id(user_id)
    normalized_company_id = _validate_company_id(company_id)
    params = (
        normalized_user_id,
        course_slug,
        normalized_company_id,
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
              AND company_id = ?
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
              AND company_id = ?
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
