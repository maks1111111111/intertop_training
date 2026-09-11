"""Owner-controlled, audited configuration of company usage limits."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from app.database.db import get_connection
from app.repositories.company_repository import CompanyRepository
from app.repositories.company_usage_limit_repository import CompanyUsageLimit, CompanyUsageLimitRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository

class PlatformUsageLimitError(ValueError): pass
class PlatformUsageLimitService:
    def __init__(self, limits: CompanyUsageLimitRepository, companies: CompanyRepository, admins: PlatformAdminRepository): self._limits, self._companies, self._admins = limits, companies, admins
    def set(self, db_path: Path, *, actor_user_id: int, company_id: str, max_active_members: Optional[int], max_courses: Optional[int], reason: str) -> CompanyUsageLimit:
        actor = self._admins.get_active_by_user_id(db_path, actor_user_id)
        if actor is None or not actor.is_owner: raise PlatformUsageLimitError("active platform owner access is required")
        if self._companies.get_by_id(db_path, company_id) is None: raise PlatformUsageLimitError("company not found")
        if not isinstance(reason, str) or not reason.strip(): raise PlatformUsageLimitError("reason is required")
        members, courses = _limit(max_active_members, "max_active_members"), _limit(max_courses, "max_courses")
        with get_connection(db_path) as c:
            usage = c.execute("SELECT (SELECT COUNT(*) FROM company_memberships WHERE company_id=? AND is_active=1), (SELECT COUNT(*) FROM courses WHERE company_id=?)", (company_id, company_id)).fetchone()
        assert usage is not None
        if members is not None and int(usage[0]) > members: raise PlatformUsageLimitError("max_active_members is below current usage")
        if courses is not None and int(usage[1]) > courses: raise PlatformUsageLimitError("max_courses is below current usage")
        result = self._limits.set(db_path, company_id, members, courses)
        self._admins.append_audit_event(db_path, actor_user_id=actor_user_id, action="company_usage_limits.updated", target_type="company", target_id=company_id, reason=reason.strip())
        return result
def _limit(value: Optional[int], field: str) -> Optional[int]:
    if value is None: return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0: raise PlatformUsageLimitError(f"{field} must be a positive integer or empty")
    return value
