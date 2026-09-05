"""Persistence for practical-task submission and AI review attempts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app.ai.review_interfaces import ReviewResult
from app.database.db import get_connection

_USER_LESSON_ATTEMPTS_FROM = """
    FROM practical_task_attempts
    JOIN users
        ON users.id = practical_task_attempts.user_id
    WHERE users.telegram_id = ?
      AND practical_task_attempts.course_slug = ?
      AND practical_task_attempts.lesson_slug = ?
"""


@dataclass(frozen=True)
class PracticalTaskReviewFeedback:
    """Reviewed practical-task feedback fields for development-profile analytics."""

    id: int
    status: str
    course_slug: str
    lesson_slug: str
    strengths: Tuple[str, ...]
    improvements: Tuple[str, ...]
    reviewed_at: Optional[str] = None


@dataclass(frozen=True)
class PracticalTaskAttemptAggregate:
    """Aggregate practical-task attempt metrics for one canonical user."""

    total_attempts_count: int
    reviewed_attempts_count: int
    passed_attempts_count: int
    failed_attempts_count: int
    pending_attempts_count: int
    scorable_attempts_count: int
    average_score_percent: Optional[float]
    best_score_percent: Optional[float]


@dataclass(frozen=True)
class PracticalTaskAttempt:
    """A stored practical-task attempt with task snapshot and review outcome."""

    id: int
    user_id: int
    telegram_id: Optional[int]
    course_slug: str
    lesson_slug: str
    task_title: str
    task_description: str
    expected_result: str
    learner_answer: str
    score: Optional[int]
    max_score: Optional[int]
    passed: Optional[bool]
    feedback_summary: Optional[str]
    strengths: Tuple[str, ...]
    improvements: Tuple[str, ...]
    status: str
    started_at: str
    reviewed_at: Optional[str]


def _deserialize_string_list(json_text: Optional[str]) -> Tuple[str, ...]:
    if json_text is None:
        return ()

    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("Feedback JSON must be a list.")

    return tuple(str(item) for item in data)


def _row_to_attempt(row: sqlite3.Row) -> PracticalTaskAttempt:
    passed_value = row["passed"]
    if passed_value is None:
        passed: Optional[bool] = None
    else:
        passed = bool(int(passed_value))

    return PracticalTaskAttempt(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        telegram_id=(
            int(row["telegram_id"])
            if row["telegram_id"] is not None
            else None
        ),
        course_slug=str(row["course_slug"]),
        lesson_slug=str(row["lesson_slug"]),
        task_title=str(row["task_title"]),
        task_description=str(row["task_description"]),
        expected_result=str(row["expected_result"]),
        learner_answer=str(row["learner_answer"]),
        score=row["score"] if row["score"] is None else int(row["score"]),
        max_score=row["max_score"] if row["max_score"] is None else int(row["max_score"]),
        passed=passed,
        feedback_summary=row["feedback_summary"],
        strengths=_deserialize_string_list(row["feedback_strengths_json"]),
        improvements=_deserialize_string_list(row["feedback_improvements_json"]),
        status=str(row["status"]),
        started_at=str(row["started_at"]),
        reviewed_at=row["reviewed_at"],
    )


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def create_attempt_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    lesson_slug: str,
    task_title: str,
    task_description: str,
    expected_result: str,
    learner_answer: str,
) -> Optional[int]:
    """Create a pending practical-task attempt for a canonical user."""
    normalized_user_id = _validate_user_id(user_id)

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO practical_task_attempts (
                user_id,
                course_slug,
                lesson_slug,
                task_title,
                task_description,
                expected_result,
                learner_answer
            )
            SELECT
                users.id,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            FROM users
            WHERE users.id = ?
            """,
            (
                course_slug,
                lesson_slug,
                task_title,
                task_description,
                expected_result,
                learner_answer,
                normalized_user_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

        return int(cursor.lastrowid)


def create_attempt(
    db_path: Path,
    telegram_id: int,
    course_slug: str,
    lesson_slug: str,
    task_title: str,
    task_description: str,
    expected_result: str,
    learner_answer: str,
) -> Optional[int]:
    """Create a pending practical-task attempt for an existing Telegram user."""
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO practical_task_attempts (
                user_id,
                course_slug,
                lesson_slug,
                task_title,
                task_description,
                expected_result,
                learner_answer
            )
            SELECT
                users.id,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            FROM users
            WHERE users.telegram_id = ?
            """,
            (
                course_slug,
                lesson_slug,
                task_title,
                task_description,
                expected_result,
                learner_answer,
                telegram_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

        return int(cursor.lastrowid)


def get_attempt(
    db_path: Path,
    attempt_id: int,
) -> Optional[PracticalTaskAttempt]:
    """Return a single attempt by id, or None if it does not exist."""
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                practical_task_attempts.*,
                users.telegram_id
            FROM practical_task_attempts
            JOIN users
                ON users.id = practical_task_attempts.user_id
            WHERE practical_task_attempts.id = ?
            """,
            (attempt_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_attempt(row)


def complete_review(
    db_path: Path,
    attempt_id: int,
    result: ReviewResult,
) -> bool:
    """Store AI review outcome for a pending attempt. Returns True if updated."""
    strengths_json = json.dumps(
        list(result.feedback.strengths),
        ensure_ascii=False,
    )
    improvements_json = json.dumps(
        list(result.feedback.improvements),
        ensure_ascii=False,
    )

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE practical_task_attempts
            SET score = ?,
                max_score = ?,
                passed = ?,
                feedback_summary = ?,
                feedback_strengths_json = ?,
                feedback_improvements_json = ?,
                status = 'reviewed',
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'pending'
            """,
            (
                result.score,
                result.max_score,
                int(result.passed),
                result.feedback.summary,
                strengths_json,
                improvements_json,
                attempt_id,
            ),
        )

        return cursor.rowcount > 0


def get_attempts_for_lesson(
    db_path: Path,
    telegram_id: int,
    course_slug: str,
    lesson_slug: str,
    limit: int = 10,
) -> list[PracticalTaskAttempt]:
    """Return recent attempts for a user, course, and lesson."""
    if limit <= 0:
        return []

    with get_connection(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                practical_task_attempts.*,
                users.telegram_id
            {_USER_LESSON_ATTEMPTS_FROM}
            ORDER BY practical_task_attempts.started_at DESC,
                     practical_task_attempts.id DESC
            LIMIT ?
            """,
            (
                telegram_id,
                course_slug,
                lesson_slug,
                limit,
            ),
        ).fetchall()

    return [_row_to_attempt(row) for row in rows]


def get_attempts_for_lesson_for_user(
    db_path: Path,
    user_id: int,
    course_slug: str,
    lesson_slug: str,
    limit: int = 10,
) -> list[PracticalTaskAttempt]:
    """Return recent lesson attempts for one canonical user."""
    normalized_user_id = _validate_user_id(user_id)
    if limit <= 0:
        return []

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                practical_task_attempts.*,
                users.telegram_id
            FROM practical_task_attempts
            JOIN users
                ON users.id = practical_task_attempts.user_id
            WHERE practical_task_attempts.user_id = ?
              AND practical_task_attempts.course_slug = ?
              AND practical_task_attempts.lesson_slug = ?
            ORDER BY practical_task_attempts.started_at DESC,
                     practical_task_attempts.id DESC
            LIMIT ?
            """,
            (
                normalized_user_id,
                course_slug,
                lesson_slug,
                limit,
            ),
        ).fetchall()

    return [_row_to_attempt(row) for row in rows]


def get_attempts_aggregate_for_user(
    db_path: Path,
    user_id: int,
) -> PracticalTaskAttemptAggregate:
    """Return aggregate practical-task metrics for one canonical user."""
    normalized_user_id = _validate_user_id(user_id)

    with get_connection(db_path) as connection:
        counts_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_attempts_count,
                SUM(CASE WHEN status = 'reviewed' THEN 1 ELSE 0 END)
                    AS reviewed_attempts_count,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)
                    AS pending_attempts_count,
                SUM(
                    CASE
                        WHEN status = 'reviewed' AND passed = 1 THEN 1
                        ELSE 0
                    END
                ) AS passed_attempts_count,
                SUM(
                    CASE
                        WHEN status = 'reviewed' AND passed = 0 THEN 1
                        ELSE 0
                    END
                ) AS failed_attempts_count
            FROM practical_task_attempts
            WHERE user_id = ?
            """,
            (normalized_user_id,),
        ).fetchone()

        score_rows = connection.execute(
            """
            SELECT score, max_score
            FROM practical_task_attempts
            WHERE user_id = ?
              AND status = 'reviewed'
              AND score IS NOT NULL
              AND max_score IS NOT NULL
              AND max_score > 0
            """,
            (normalized_user_id,),
        ).fetchall()

    score_percents = [
        round(int(row["score"]) * 100 / int(row["max_score"]), 2)
        for row in score_rows
    ]

    return PracticalTaskAttemptAggregate(
        total_attempts_count=int(counts_row["total_attempts_count"]),
        reviewed_attempts_count=int(counts_row["reviewed_attempts_count"] or 0),
        passed_attempts_count=int(counts_row["passed_attempts_count"] or 0),
        failed_attempts_count=int(counts_row["failed_attempts_count"] or 0),
        pending_attempts_count=int(counts_row["pending_attempts_count"] or 0),
        scorable_attempts_count=len(score_percents),
        average_score_percent=(
            round(sum(score_percents) / len(score_percents), 2)
            if score_percents
            else None
        ),
        best_score_percent=max(score_percents) if score_percents else None,
    )


def get_attempts_for_user(
    db_path: Path,
    user_id: int,
    limit: int = 10,
) -> list[PracticalTaskAttempt]:
    """Return recent practical-task attempts for one canonical user."""
    normalized_user_id = _validate_user_id(user_id)
    if limit <= 0:
        return []

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                practical_task_attempts.*,
                users.telegram_id
            FROM practical_task_attempts
            JOIN users
                ON users.id = practical_task_attempts.user_id
            WHERE practical_task_attempts.user_id = ?
            ORDER BY practical_task_attempts.started_at DESC,
                     practical_task_attempts.id DESC
            LIMIT ?
            """,
            (
                normalized_user_id,
                limit,
            ),
        ).fetchall()

    return [_row_to_attempt(row) for row in rows]


def get_reviewed_feedback_for_user(
    db_path: Path,
    user_id: int,
) -> list[PracticalTaskReviewFeedback]:
    """Return reviewed practical-task feedback for one canonical user."""
    normalized_user_id = _validate_user_id(user_id)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                status,
                course_slug,
                lesson_slug,
                feedback_strengths_json,
                feedback_improvements_json,
                reviewed_at
            FROM practical_task_attempts
            WHERE user_id = ?
              AND status = 'reviewed'
            ORDER BY reviewed_at ASC, id ASC
            """,
            (normalized_user_id,),
        ).fetchall()

    return [
        PracticalTaskReviewFeedback(
            id=int(row["id"]),
            status=str(row["status"]),
            course_slug=str(row["course_slug"]),
            lesson_slug=str(row["lesson_slug"]),
            strengths=_deserialize_string_list(row["feedback_strengths_json"]),
            improvements=_deserialize_string_list(row["feedback_improvements_json"]),
            reviewed_at=row["reviewed_at"],
        )
        for row in rows
    ]
