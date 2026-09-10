"""Tenant-scoped persistence for course enrollment and lesson progress."""

from pathlib import Path
from typing import Optional, Tuple

from app.database.db import get_connection

LEGACY_COMPANY_ID = "intertop"


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")
    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")
    return normalized


def _ensure_legacy_company(connection, company_id: str) -> None:
    """Provision only the pre-SaaS default for backward-compatible callers."""
    if company_id == LEGACY_COMPANY_ID:
        connection.execute(
            """INSERT INTO companies (id, name) VALUES (?, 'Intertop')
               ON CONFLICT(id) DO NOTHING""",
            (company_id,),
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


def _validate_due_at(due_at: Optional[str]) -> Optional[str]:
    if due_at is None:
        return None
    if not isinstance(due_at, str) or not due_at.strip():
        raise ValueError("due_at must be a non-empty string or None")
    return due_at.strip()


_ALLOWED_DEVELOPMENT_SOURCES = frozenset({"quiz", "practical"})
_MAX_DEVELOPMENT_REASON_LENGTH = 200


def _validate_development_context(
    development_source: Optional[str], development_reason: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    if development_source is None and development_reason is None:
        return None, None
    source = (development_source or "").strip()
    reason = (development_reason or "").strip()
    if source not in _ALLOWED_DEVELOPMENT_SOURCES or not reason:
        raise ValueError("invalid development context")
    if len(reason) > _MAX_DEVELOPMENT_REASON_LENGTH:
        raise ValueError("development_reason is too long")
    return source, reason


class ProgressRepository:
    """Saves and retrieves learning progress within one tenant."""

    # Telegram has no company selector yet. Its legacy flows are deliberately
    # confined to the tenant that received all pre-SaaS data during migration.
    def start_course(self, db_path: Path, telegram_id: int, course_slug: str) -> None:
        with get_connection(db_path) as connection:
            connection.execute(
                """INSERT INTO companies (id, name) VALUES (?, 'Intertop')
                   ON CONFLICT(id) DO NOTHING""",
                (LEGACY_COMPANY_ID,),
            )
            connection.execute(
                """INSERT INTO enrollments (
                       company_id, user_id, course_id, status, progress_percent, started_at
                   ) SELECT ?, users.id, courses.id, 'in_progress', 0, CURRENT_TIMESTAMP
                     FROM users JOIN courses ON courses.slug = ? AND courses.company_id = ? WHERE users.telegram_id = ?
                   ON CONFLICT(company_id, user_id, course_id) DO UPDATE SET
                     status = CASE WHEN enrollments.status = 'completed'
                       THEN enrollments.status ELSE 'in_progress' END,
                     started_at = COALESCE(enrollments.started_at, CURRENT_TIMESTAMP)""",
                (LEGACY_COMPANY_ID, course_slug, LEGACY_COMPANY_ID, telegram_id),
            )

    def get_resume_lesson_index(self, db_path: Path, telegram_id: int, course_slug: str) -> int:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS completed_count FROM lesson_progress
                   JOIN users ON users.id = lesson_progress.user_id
                   JOIN lessons ON lessons.id = lesson_progress.lesson_id
                   JOIN courses ON courses.id = lessons.course_id
                   WHERE users.telegram_id = ? AND courses.slug = ? AND courses.company_id = ?
                     AND lesson_progress.company_id = ? AND lesson_progress.status = 'completed'""",
                (telegram_id, course_slug, LEGACY_COMPANY_ID, LEGACY_COMPANY_ID),
            ).fetchone()
        return int(row["completed_count"]) if row else 0

    def complete_lesson(self, db_path: Path, telegram_id: int, course_slug: str, lesson_slug: str) -> None:
        with get_connection(db_path) as connection:
            user = connection.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if user is not None:
            self.complete_lesson_for_user(db_path, int(user["id"]), course_slug, lesson_slug, LEGACY_COMPANY_ID)

    def complete_course(self, db_path: Path, telegram_id: int, course_slug: str) -> None:
        with get_connection(db_path) as connection:
            connection.execute(
                """UPDATE enrollments SET status = 'completed', progress_percent = 100,
                   completed_at = CURRENT_TIMESTAMP WHERE company_id = ?
                   AND user_id = (SELECT id FROM users WHERE telegram_id = ?)
                   AND course_id = (SELECT id FROM courses WHERE slug = ? AND company_id = ?)""",
                (LEGACY_COMPANY_ID, telegram_id, course_slug, LEGACY_COMPANY_ID),
            )

    def get_course_progress(self, db_path: Path, telegram_id: int, course_slug: str) -> Tuple[str, int]:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """SELECT enrollments.status, enrollments.progress_percent FROM enrollments
                   JOIN users ON users.id = enrollments.user_id
                   JOIN courses ON courses.id = enrollments.course_id
                   WHERE users.telegram_id = ? AND courses.slug = ? AND courses.company_id = ? AND enrollments.company_id = ?""",
                (telegram_id, course_slug, LEGACY_COMPANY_ID, LEGACY_COMPANY_ID),
            ).fetchone()
        return (str(row["status"]), int(row["progress_percent"])) if row else ("not_started", 0)

    def assign_course_to_user(self, db_path: Path, user_id: int, course_slug: str, *, assigned_by_user_id: Optional[int] = None, due_at: Optional[str] = None, development_source: Optional[str] = None, development_reason: Optional[str] = None, company_id: str = LEGACY_COMPANY_ID) -> bool:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        assigned_by_user_id = None if assigned_by_user_id is None else _validate_user_id(assigned_by_user_id)
        due_at = _validate_due_at(due_at)
        development_source, development_reason = _validate_development_context(development_source, development_reason)
        with get_connection(db_path) as connection:
            _ensure_legacy_company(connection, company_id)
            if not _has_active_membership(connection, company_id, user_id):
                return False
            if (
                assigned_by_user_id is not None
                and not _has_active_membership(
                    connection,
                    company_id,
                    assigned_by_user_id,
                )
            ):
                return False
            if assigned_by_user_id is not None and connection.execute("SELECT 1 FROM users WHERE id = ?", (assigned_by_user_id,)).fetchone() is None:
                return False
            connection.execute(
                """INSERT INTO enrollments (company_id, user_id, course_id, status, progress_percent,
                       assigned_by_user_id, due_at, development_source, development_reason, started_at, completed_at)
                   SELECT ?, ?, courses.id, 'assigned', 0, ?, ?, ?, ?, NULL, NULL
                   FROM courses WHERE courses.slug = ? AND courses.company_id = ? AND EXISTS (SELECT 1 FROM users WHERE users.id = ?)
                   ON CONFLICT(company_id, user_id, course_id) DO NOTHING""",
                (company_id, user_id, assigned_by_user_id, due_at, development_source, development_reason, course_slug, company_id, user_id),
            )
            row = connection.execute(
                """SELECT 1 FROM enrollments JOIN courses ON courses.id = enrollments.course_id
                   WHERE enrollments.company_id = ? AND enrollments.user_id = ? AND courses.slug = ? AND courses.company_id = ?""",
                (company_id, user_id, course_slug, company_id),
            ).fetchone()
        return row is not None

    def get_assigned_courses_for_user(self, db_path: Path, user_id: int, company_id: str = LEGACY_COMPANY_ID) -> list[Tuple[str, str, str]]:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """SELECT courses.slug, courses.title, enrollments.assigned_at FROM enrollments
                   JOIN courses ON courses.id = enrollments.course_id WHERE enrollments.company_id = ? AND courses.company_id = ?
                   AND enrollments.user_id = ? AND enrollments.status = 'assigned'
                   ORDER BY enrollments.assigned_at ASC, courses.id ASC, courses.title ASC""",
                (company_id, company_id, user_id),
            ).fetchall()
        return [(str(r["slug"]), str(r["title"]), str(r["assigned_at"])) for r in rows]

    def start_course_for_user(self, db_path: Path, user_id: int, course_slug: str, company_id: str = LEGACY_COMPANY_ID) -> None:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            _ensure_legacy_company(connection, company_id)
            if not _has_active_membership(connection, company_id, user_id):
                return
            connection.execute(
                """INSERT INTO enrollments (company_id, user_id, course_id, status, progress_percent, started_at)
                   SELECT ?, ?, courses.id, 'in_progress', 0, CURRENT_TIMESTAMP FROM courses
                   WHERE courses.slug = ? AND courses.company_id = ? AND EXISTS (SELECT 1 FROM users WHERE users.id = ?)
                   ON CONFLICT(company_id, user_id, course_id) DO UPDATE SET
                   status = CASE WHEN enrollments.status = 'completed' THEN enrollments.status ELSE 'in_progress' END,
                   started_at = COALESCE(enrollments.started_at, CURRENT_TIMESTAMP)""",
                (company_id, user_id, course_slug, company_id, user_id),
            )

    def get_resume_lesson_index_for_user(self, db_path: Path, user_id: int, course_slug: str, company_id: str = LEGACY_COMPANY_ID) -> int:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS completed_count FROM lesson_progress JOIN lessons ON lessons.id = lesson_progress.lesson_id
                   JOIN courses ON courses.id = lessons.course_id WHERE lesson_progress.company_id = ?
                   AND lesson_progress.user_id = ? AND courses.slug = ? AND courses.company_id = ? AND lesson_progress.status = 'completed'""",
                (company_id, user_id, course_slug, company_id),
            ).fetchone()
        return int(row["completed_count"]) if row else 0

    def complete_lesson_for_user(self, db_path: Path, user_id: int, course_slug: str, lesson_slug: str, company_id: str = LEGACY_COMPANY_ID) -> None:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            _ensure_legacy_company(connection, company_id)
            if not _has_active_membership(connection, company_id, user_id):
                return
            connection.execute(
                """INSERT INTO lesson_progress (company_id, user_id, lesson_id, status, started_at, completed_at)
                   SELECT ?, ?, lessons.id, 'completed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM courses
                   JOIN lessons ON lessons.course_id = courses.id AND lessons.slug = ? WHERE courses.slug = ? AND courses.company_id = ?
                   AND EXISTS (SELECT 1 FROM users WHERE users.id = ?)
                   ON CONFLICT(company_id, user_id, lesson_id) DO UPDATE SET status = 'completed',
                   started_at = COALESCE(lesson_progress.started_at, CURRENT_TIMESTAMP), completed_at = CURRENT_TIMESTAMP""",
                (company_id, user_id, lesson_slug, course_slug, company_id, user_id),
            )
            totals = connection.execute(
                """SELECT courses.id AS course_id, COUNT(lessons.id) AS total_lessons,
                   SUM(CASE WHEN lesson_progress.status = 'completed' THEN 1 ELSE 0 END) AS completed_lessons
                   FROM courses JOIN lessons ON lessons.course_id = courses.id LEFT JOIN lesson_progress
                   ON lesson_progress.lesson_id = lessons.id AND lesson_progress.user_id = ?
                   AND lesson_progress.company_id = ? WHERE courses.slug = ? AND courses.company_id = ? GROUP BY courses.id""",
                (user_id, company_id, course_slug, company_id),
            ).fetchone()
            if totals is None or int(totals["total_lessons"]) == 0:
                return
            progress = round(int(totals["completed_lessons"]) * 100 / int(totals["total_lessons"]))
            connection.execute("UPDATE enrollments SET progress_percent = ? WHERE company_id = ? AND user_id = ? AND course_id = ?", (progress, company_id, user_id, totals["course_id"]))

    def complete_course_for_user(self, db_path: Path, user_id: int, course_slug: str, company_id: str = LEGACY_COMPANY_ID) -> None:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            if not _has_active_membership(connection, company_id, user_id):
                return
            connection.execute("""UPDATE enrollments SET status = 'completed', progress_percent = 100, completed_at = CURRENT_TIMESTAMP
                WHERE company_id = ? AND user_id = ? AND course_id = (SELECT id FROM courses WHERE slug = ? AND company_id = ?)""", (company_id, user_id, course_slug, company_id))

    def get_course_progress_for_user(self, db_path: Path, user_id: int, course_slug: str, company_id: str = LEGACY_COMPANY_ID) -> Tuple[str, int]:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            row = connection.execute("""SELECT enrollments.status, enrollments.progress_percent FROM enrollments JOIN courses ON courses.id = enrollments.course_id
                WHERE enrollments.company_id = ? AND enrollments.user_id = ? AND courses.slug = ? AND courses.company_id = ?""", (company_id, user_id, course_slug, company_id)).fetchone()
        return (str(row["status"]), int(row["progress_percent"])) if row else ("not_started", 0)

    def get_latest_in_progress_course_for_user(self, db_path: Path, user_id: int, company_id: str = LEGACY_COMPANY_ID) -> Optional[Tuple[str, int]]:
        user_id, company_id = _validate_user_id(user_id), _validate_company_id(company_id)
        with get_connection(db_path) as connection:
            row = connection.execute("""SELECT courses.slug, enrollments.progress_percent FROM enrollments JOIN courses ON courses.id = enrollments.course_id
                WHERE enrollments.company_id = ? AND courses.company_id = ? AND enrollments.user_id = ? AND enrollments.status = 'in_progress'
                ORDER BY enrollments.started_at DESC, courses.id DESC LIMIT 1""", (company_id, company_id, user_id)).fetchone()
        return (str(row["slug"]), int(row["progress_percent"])) if row else None

    def get_latest_in_progress_course(self, db_path: Path, telegram_id: int) -> Optional[Tuple[str, int]]:
        with get_connection(db_path) as connection:
            row = connection.execute("""SELECT courses.slug, enrollments.progress_percent FROM enrollments JOIN users ON users.id = enrollments.user_id
                JOIN courses ON courses.id = enrollments.course_id WHERE enrollments.company_id = ? AND courses.company_id = ? AND users.telegram_id = ?
                AND enrollments.status = 'in_progress' ORDER BY enrollments.started_at DESC, courses.id DESC LIMIT 1""", (LEGACY_COMPANY_ID, LEGACY_COMPANY_ID, telegram_id)).fetchone()
        return (str(row["slug"]), int(row["progress_percent"])) if row else None
