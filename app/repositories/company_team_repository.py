"""Tenant-scoped learning summary for company members."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class CompanyTeamMemberRecord:
    """Persisted learning summary for one active company member."""

    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    role: str
    started_courses_count: int
    completed_courses_count: int
    average_progress_percent: int


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")

    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")

    return normalized


class CompanyTeamRepository:
    """Read tenant-scoped company member learning summaries."""

    def list_learning_summary(
        self,
        db_path: Path,
        company_id: str,
    ) -> tuple[CompanyTeamMemberRecord, ...]:
        """Return active members and aggregate enrollment progress for one company."""
        normalized_company_id = _validate_company_id(company_id)

        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                WITH progress AS (
                    SELECT
                        user_id,
                        COUNT(*) AS started_courses_count,
                        SUM(
                            CASE
                                WHEN status = 'completed' THEN 1
                                ELSE 0
                            END
                        ) AS completed_courses_count,
                        ROUND(
                            AVG(progress_percent)
                        ) AS average_progress_percent
                    FROM enrollments
                    WHERE status IN ('in_progress', 'completed')
                    GROUP BY user_id
                )
                SELECT
                    users.id AS user_id,
                    users.username,
                    users.first_name,
                    users.last_name,
                    company_memberships.role,
                    COALESCE(
                        progress.started_courses_count,
                        0
                    ) AS started_courses_count,
                    COALESCE(
                        progress.completed_courses_count,
                        0
                    ) AS completed_courses_count,
                    COALESCE(
                        progress.average_progress_percent,
                        0
                    ) AS average_progress_percent
                FROM company_memberships
                JOIN users
                    ON users.id = company_memberships.user_id
                LEFT JOIN progress
                    ON progress.user_id = users.id
                WHERE company_memberships.company_id = ?
                  AND company_memberships.is_active = 1
                  AND users.is_active = 1
                ORDER BY
                    users.first_name COLLATE NOCASE,
                    users.last_name COLLATE NOCASE,
                    users.username COLLATE NOCASE,
                    users.id
                """,
                (normalized_company_id,),
            ).fetchall()

        return tuple(
            CompanyTeamMemberRecord(
                user_id=int(row["user_id"]),
                username=(
                    str(row["username"])
                    if row["username"] is not None
                    else None
                ),
                first_name=(
                    str(row["first_name"])
                    if row["first_name"] is not None
                    else None
                ),
                last_name=(
                    str(row["last_name"])
                    if row["last_name"] is not None
                    else None
                ),
                role=str(row["role"]),
                started_courses_count=int(row["started_courses_count"]),
                completed_courses_count=int(row["completed_courses_count"]),
                average_progress_percent=int(
                    row["average_progress_percent"]
                ),
            )
            for row in rows
        )
