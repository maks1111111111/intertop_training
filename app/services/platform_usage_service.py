"""Read-only aggregate usage metrics for global platform operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.database.db import get_connection


@dataclass(frozen=True)
class CompanyUsage:
    company_id: str
    company_name: str
    is_active: bool
    active_members: int
    courses: int
    active_enrollments: int
    active_documents: int


@dataclass(frozen=True)
class PlatformUsageOverview:
    active_companies: int
    active_members: int
    courses: int
    active_enrollments: int
    active_documents: int
    companies: tuple[CompanyUsage, ...]


class PlatformUsageService:
    """Read aggregate tenant counts without exposing user-level records."""

    def get_overview(self, db_path: Path) -> PlatformUsageOverview:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    companies.id AS company_id,
                    companies.name AS company_name,
                    companies.is_active AS is_active,
                    (SELECT COUNT(*) FROM company_memberships
                     WHERE company_memberships.company_id = companies.id
                       AND company_memberships.is_active = 1) AS active_members,
                    (SELECT COUNT(*) FROM courses
                     WHERE courses.company_id = companies.id) AS courses,
                    (SELECT COUNT(*) FROM enrollments
                     WHERE enrollments.company_id = companies.id
                       AND enrollments.status != 'completed') AS active_enrollments,
                    (SELECT COUNT(*) FROM knowledge_documents
                     WHERE knowledge_documents.company_id = companies.id
                       AND knowledge_documents.status = 'active') AS active_documents
                FROM companies
                ORDER BY companies.is_active DESC, companies.id ASC
                """
            ).fetchall()

        companies = tuple(
            CompanyUsage(
                company_id=str(row["company_id"]),
                company_name=str(row["company_name"]),
                is_active=bool(row["is_active"]),
                active_members=int(row["active_members"]),
                courses=int(row["courses"]),
                active_enrollments=int(row["active_enrollments"]),
                active_documents=int(row["active_documents"]),
            )
            for row in rows
        )
        active_companies = tuple(company for company in companies if company.is_active)
        return PlatformUsageOverview(
            active_companies=len(active_companies),
            active_members=sum(company.active_members for company in active_companies),
            courses=sum(company.courses for company in active_companies),
            active_enrollments=sum(
                company.active_enrollments for company in active_companies
            ),
            active_documents=sum(
                company.active_documents for company in active_companies
            ),
            companies=companies,
        )
