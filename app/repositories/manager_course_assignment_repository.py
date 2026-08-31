"""Tenant-scoped persisted course assignments for manager views."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class ManagerCourseAssignmentRecord:
    """One explicit manager-authored course assignment for an employee."""

    employee_user_id: int
    course_slug: str
    course_title: str
    status: str
    progress_percent: int
    assigned_at: str
    assigned_by_user_id: int
    started_at: Optional[str]
    completed_at: Optional[str]


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")

    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")

    return normalized


def _validate_user_id(user_id: int) -> int:
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        raise ValueError("user_id must be a positive integer")

    return user_id


class ManagerCourseAssignmentRepository:
    """Read explicit course assignments for tenant-scoped employees."""

    def list_for_member(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
    ) -> tuple[ManagerCourseAssignmentRecord, ...]:
        """Return explicit manager assignments for one active company member."""
        normalized_company_id = _validate_company_id(company_id)
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    enrollments.user_id AS employee_user_id,
                    courses.slug AS course_slug,
                    courses.title AS course_title,
                    enrollments.status,
                    enrollments.progress_percent,
                    enrollments.assigned_at,
                    enrollments.assigned_by_user_id,
                    enrollments.started_at,
                    enrollments.completed_at
                FROM company_memberships
                JOIN users
                    ON users.id = company_memberships.user_id
                JOIN enrollments
                    ON enrollments.user_id = users.id
                JOIN courses
                    ON courses.id = enrollments.course_id
                WHERE company_memberships.company_id = ?
                  AND company_memberships.user_id = ?
                  AND company_memberships.is_active = 1
                  AND users.is_active = 1
                  AND enrollments.assigned_by_user_id IS NOT NULL
                ORDER BY
                    enrollments.assigned_at DESC,
                    enrollments.id DESC
                """,
                (
                    normalized_company_id,
                    normalized_user_id,
                ),
            ).fetchall()

        return tuple(
            ManagerCourseAssignmentRecord(
                employee_user_id=int(row["employee_user_id"]),
                course_slug=str(row["course_slug"]),
                course_title=str(row["course_title"]),
                status=str(row["status"]),
                progress_percent=int(row["progress_percent"]),
                assigned_at=str(row["assigned_at"]),
                assigned_by_user_id=int(row["assigned_by_user_id"]),
                started_at=(
                    str(row["started_at"])
                    if row["started_at"] is not None
                    else None
                ),
                completed_at=(
                    str(row["completed_at"])
                    if row["completed_at"] is not None
                    else None
                ),
            )
            for row in rows
        )
