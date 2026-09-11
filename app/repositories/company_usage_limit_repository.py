"""Persistence for explicit per-company SaaS usage limits."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from app.database.db import get_connection

@dataclass(frozen=True)
class CompanyUsageLimit:
    company_id: str
    max_active_members: Optional[int]
    max_courses: Optional[int]

class CompanyUsageLimitRepository:
    def get(self, db_path: Path, company_id: str) -> CompanyUsageLimit:
        with get_connection(db_path) as connection:
            row = connection.execute("SELECT * FROM company_usage_limits WHERE company_id = ?", (company_id,)).fetchone()
        if row is None:
            return CompanyUsageLimit(company_id, None, None)
        return CompanyUsageLimit(str(row["company_id"]), row["max_active_members"], row["max_courses"])

    def set(self, db_path: Path, company_id: str, max_active_members: Optional[int], max_courses: Optional[int]) -> CompanyUsageLimit:
        with get_connection(db_path) as connection:
            connection.execute("""INSERT INTO company_usage_limits (company_id, max_active_members, max_courses) VALUES (?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET max_active_members=excluded.max_active_members, max_courses=excluded.max_courses, updated_at=CURRENT_TIMESTAMP""", (company_id, max_active_members, max_courses))
        return self.get(db_path, company_id)
