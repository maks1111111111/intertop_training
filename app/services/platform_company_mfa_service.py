"""Owner-only recovery controls for tenant administrator MFA."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.database.db import get_connection
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.repositories.user_mfa_repository import UserMFARepository


@dataclass(frozen=True)
class CompanyAdminMFAStatus:
    company_id: str
    user_id: int
    email: str
    display_name: str
    is_enrolled: bool


class PlatformCompanyMFAError(ValueError):
    """Raised when an owner-only MFA recovery operation is rejected."""


class PlatformCompanyMFAService:
    """List tenant admin MFA state and audit owner-authorized resets."""

    def __init__(
        self,
        mfa_repository: UserMFARepository,
        platform_admin_repository: PlatformAdminRepository,
    ) -> None:
        self._mfa = mfa_repository
        self._platform_admins = platform_admin_repository

    def list_admins(self, db_path: Path) -> tuple[CompanyAdminMFAStatus, ...]:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    memberships.company_id,
                    users.id AS user_id,
                    credentials.email,
                    COALESCE(
                        NULLIF(TRIM(
                            COALESCE(users.first_name, '') || ' ' ||
                            COALESCE(users.last_name, '')
                        ), ''),
                        credentials.email
                    ) AS display_name,
                    COALESCE(mfa.is_active, 0) AS mfa_is_active
                FROM company_memberships AS memberships
                JOIN users ON users.id = memberships.user_id
                JOIN user_password_credentials AS credentials
                  ON credentials.user_id = users.id
                LEFT JOIN user_mfa_credentials AS mfa
                  ON mfa.user_id = users.id
                WHERE memberships.role = 'admin'
                  AND memberships.is_active = 1
                  AND users.is_active = 1
                  AND credentials.is_active = 1
                ORDER BY memberships.company_id, credentials.email COLLATE NOCASE
                """
            ).fetchall()
        return tuple(
            CompanyAdminMFAStatus(
                company_id=str(row["company_id"]),
                user_id=int(row["user_id"]),
                email=str(row["email"]),
                display_name=str(row["display_name"]),
                is_enrolled=bool(row["mfa_is_active"]),
            )
            for row in rows
        )

    def reset(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        company_id: str,
        target_user_id: int,
        reason: str,
    ) -> None:
        owner = self._platform_admins.get_active_by_user_id(
            db_path,
            actor_user_id,
        )
        if owner is None or not owner.is_owner:
            raise PlatformCompanyMFAError(
                "active platform owner access is required"
            )
        normalized_company_id = _required(company_id, "company_id")
        normalized_reason = _required(reason, "reason")
        if (
            not isinstance(target_user_id, int)
            or isinstance(target_user_id, bool)
            or target_user_id <= 0
        ):
            raise PlatformCompanyMFAError("target_user_id is invalid")
        with get_connection(db_path) as connection:
            target = connection.execute(
                """
                SELECT 1
                FROM company_memberships
                JOIN users ON users.id = company_memberships.user_id
                WHERE company_memberships.company_id = ?
                  AND company_memberships.user_id = ?
                  AND company_memberships.role = 'admin'
                  AND company_memberships.is_active = 1
                  AND users.is_active = 1
                """,
                (normalized_company_id, target_user_id),
            ).fetchone()
        if target is None:
            raise PlatformCompanyMFAError("Администратор компании не найден.")
        if not self._mfa.delete(db_path, target_user_id):
            raise PlatformCompanyMFAError("MFA для администратора ещё не подключена.")
        self._platform_admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="company_admin.mfa_reset",
            target_type="user",
            target_id=str(target_user_id),
            reason=f"company={normalized_company_id}; {normalized_reason}",
        )


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise PlatformCompanyMFAError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise PlatformCompanyMFAError(f"{field_name} is required")
    return normalized
