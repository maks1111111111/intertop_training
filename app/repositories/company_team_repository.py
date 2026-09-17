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
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    manager_user_id: Optional[int] = None
    manager_name: Optional[str] = None


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
        department_id: Optional[int] = None,
    ) -> tuple[CompanyTeamMemberRecord, ...]:
        """Return active members and aggregate enrollment progress for one company."""
        normalized_company_id = _validate_company_id(company_id)

        with get_connection(db_path) as connection:
            membership_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(company_memberships)")
            }
            has_department_data = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'company_member_organizations'"
            ).fetchone() is not None
            department_select = (
                """organization.department_id, company_departments.name AS department_name,
                    organization.manager_user_id,
                    COALESCE(manager.first_name, manager.username) AS manager_name,"""
                if has_department_data
                else "NULL AS department_id, NULL AS department_name, NULL AS manager_user_id, NULL AS manager_name,"
            )
            department_join = (
                """LEFT JOIN company_member_organizations AS organization
                    ON organization.company_id = company_memberships.company_id
                   AND organization.user_id = company_memberships.user_id
                LEFT JOIN company_departments
                    ON company_departments.id = organization.department_id
                   AND company_departments.company_id = company_memberships.company_id
                LEFT JOIN users AS manager
                    ON manager.id = organization.manager_user_id"""
                if has_department_data
                else ""
            )
            enrollment_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(enrollments)")
            }
            tenant_filter = (
                "AND enrollments.company_id = ?"
                if "company_id" in enrollment_columns
                else ""
            )
            course_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(courses)")
            }
            course_tenant_join = ""
            course_tenant_params: tuple[str, ...] = ()
            if (
                {"company_id", "course_id"}.issubset(enrollment_columns)
                and "company_id" in course_columns
            ):
                course_tenant_join = """
                    JOIN courses
                        ON courses.id = enrollments.course_id
                       AND courses.company_id = ?
                """
                course_tenant_params = (normalized_company_id,)
            department_filter = ""
            department_params: tuple[object, ...] = ()
            if department_id is not None:
                if not isinstance(department_id, int) or isinstance(department_id, bool) or department_id <= 0:
                    raise ValueError("department_id must be a positive integer")
                if not has_department_data:
                    return ()
                department_filter = " AND organization.department_id = ?"
                department_params = (department_id,)
            rows = connection.execute(
                f"""
                WITH progress AS (
                    SELECT
                        enrollments.user_id,
                        COUNT(*) AS started_courses_count,
                        SUM(
                            CASE
                                WHEN enrollments.status = 'completed' THEN 1
                                ELSE 0
                            END
                        ) AS completed_courses_count,
                        ROUND(
                            AVG(enrollments.progress_percent)
                        ) AS average_progress_percent
                    FROM enrollments
                    {course_tenant_join}
                    WHERE enrollments.status IN ('in_progress', 'completed') {tenant_filter}
                    GROUP BY enrollments.user_id
                )
                SELECT
                    users.id AS user_id,
                    users.username,
                    users.first_name,
                    users.last_name,
                    company_memberships.role,
                    {department_select}
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
                {department_join}
                LEFT JOIN progress
                    ON progress.user_id = users.id
                WHERE company_memberships.company_id = ?
                  AND company_memberships.is_active = 1
                  AND users.is_active = 1
                  {department_filter}
                ORDER BY
                    users.first_name COLLATE NOCASE,
                    users.last_name COLLATE NOCASE,
                    users.username COLLATE NOCASE,
                    users.id
                """,
                course_tenant_params
                + ((normalized_company_id,) if tenant_filter else ())
                + (normalized_company_id,)
                + department_params,
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
                department_id=(int(row["department_id"]) if row["department_id"] is not None else None),
                department_name=(str(row["department_name"]) if row["department_name"] is not None else None),
                manager_user_id=(int(row["manager_user_id"]) if row["manager_user_id"] is not None else None),
                manager_name=(str(row["manager_name"]) if row["manager_name"] is not None else None),
            )
            for row in rows
        )

    def get_learning_summary(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
        department_id: Optional[int] = None,
    ) -> Optional[CompanyTeamMemberRecord]:
        """Return one active member summary scoped to one company."""
        normalized_company_id = _validate_company_id(company_id)
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        with get_connection(db_path) as connection:
            membership_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(company_memberships)")
            }
            has_department_data = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'company_member_organizations'"
            ).fetchone() is not None
            department_select = (
                """organization.department_id, company_departments.name AS department_name,
                    organization.manager_user_id,
                    COALESCE(manager.first_name, manager.username) AS manager_name,"""
                if has_department_data
                else "NULL AS department_id, NULL AS department_name, NULL AS manager_user_id, NULL AS manager_name,"
            )
            department_join = (
                """LEFT JOIN company_member_organizations AS organization
                    ON organization.company_id = company_memberships.company_id
                   AND organization.user_id = company_memberships.user_id
                LEFT JOIN company_departments
                    ON company_departments.id = organization.department_id
                   AND company_departments.company_id = company_memberships.company_id
                LEFT JOIN users AS manager
                    ON manager.id = organization.manager_user_id"""
                if has_department_data
                else ""
            )
            enrollment_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(enrollments)")
            }
            tenant_filter = (
                "AND enrollments.company_id = ?"
                if "company_id" in enrollment_columns
                else ""
            )
            course_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(courses)")
            }
            course_tenant_join = ""
            course_tenant_params: tuple[str, ...] = ()
            if (
                {"company_id", "course_id"}.issubset(enrollment_columns)
                and "company_id" in course_columns
            ):
                course_tenant_join = """
                    JOIN courses
                        ON courses.id = enrollments.course_id
                       AND courses.company_id = ?
                """
                course_tenant_params = (normalized_company_id,)
            department_filter = ""
            department_params: tuple[object, ...] = ()
            if department_id is not None:
                if not isinstance(department_id, int) or isinstance(department_id, bool) or department_id <= 0:
                    raise ValueError("department_id must be a positive integer")
                if not has_department_data:
                    return None
                department_filter = " AND organization.department_id = ?"
                department_params = (department_id,)
            row = connection.execute(
                f"""
                WITH progress AS (
                    SELECT
                        enrollments.user_id,
                        COUNT(*) AS started_courses_count,
                        SUM(
                            CASE
                                WHEN enrollments.status = 'completed' THEN 1
                                ELSE 0
                            END
                        ) AS completed_courses_count,
                        ROUND(AVG(enrollments.progress_percent)) AS average_progress_percent
                    FROM enrollments
                    {course_tenant_join}
                    WHERE enrollments.status IN ('in_progress', 'completed') {tenant_filter}
                    GROUP BY enrollments.user_id
                )
                SELECT
                    users.id AS user_id,
                    users.username,
                    users.first_name,
                    users.last_name,
                    company_memberships.role,
                    {department_select}
                    COALESCE(progress.started_courses_count, 0)
                        AS started_courses_count,
                    COALESCE(progress.completed_courses_count, 0)
                        AS completed_courses_count,
                    COALESCE(progress.average_progress_percent, 0)
                        AS average_progress_percent
                FROM company_memberships
                JOIN users
                    ON users.id = company_memberships.user_id
                {department_join}
                LEFT JOIN progress
                    ON progress.user_id = users.id
                WHERE company_memberships.company_id = ?
                  AND company_memberships.user_id = ?
                  AND company_memberships.is_active = 1
                  AND users.is_active = 1
                  {department_filter}
                LIMIT 1
                """,
                course_tenant_params
                + ((normalized_company_id,) if tenant_filter else ())
                + (normalized_company_id, user_id)
                + department_params,
            ).fetchone()

        if row is None:
            return None

        return CompanyTeamMemberRecord(
            user_id=int(row["user_id"]),
            username=str(row["username"]) if row["username"] is not None else None,
            first_name=str(row["first_name"]) if row["first_name"] is not None else None,
            last_name=str(row["last_name"]) if row["last_name"] is not None else None,
            role=str(row["role"]),
            started_courses_count=int(row["started_courses_count"]),
            completed_courses_count=int(row["completed_courses_count"]),
            average_progress_percent=int(row["average_progress_percent"]),
            department_id=(int(row["department_id"]) if row["department_id"] is not None else None),
            department_name=(str(row["department_name"]) if row["department_name"] is not None else None),
            manager_user_id=(int(row["manager_user_id"]) if row["manager_user_id"] is not None else None),
            manager_name=(str(row["manager_name"]) if row["manager_name"] is not None else None),
        )
