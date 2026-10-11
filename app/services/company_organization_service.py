"""Role-bound department and team provisioning inside a company."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection
from app.repositories.company_department_repository import CompanyDepartment
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.services.company_user_provisioning_service import (
    CompanyUserProvisioningError,
    CompanyUserProvisioningService,
    ProvisionedCompanyUser,
)


class CompanyOrganizationError(ValueError):
    """Raised when an organization operation violates the role hierarchy."""


@dataclass(frozen=True)
class CompanyManager:
    """A manager visible to a company administrator in the team workspace."""

    user_id: int
    display_name: str
    email: str
    department_name: str | None
    is_active: bool


class CompanyOrganizationService:
    """Apply owner/admin/manager boundaries to company setup operations."""

    def __init__(
        self,
        provisioning: Optional[CompanyUserProvisioningService] = None,
        membership_repository: Optional[CompanyMembershipRepository] = None,
        platform_admin_repository: Optional[PlatformAdminRepository] = None,
    ) -> None:
        self._provisioning = provisioning or CompanyUserProvisioningService()
        self._memberships = membership_repository or CompanyMembershipRepository()
        self._platform_admins = platform_admin_repository or PlatformAdminRepository()

    def create_department(self, db_path: Path, *, actor_user_id: int, company_id: str, name: str) -> CompanyDepartment:
        self._require_role(db_path, actor_user_id, company_id, "admin")
        normalized_name = _required(name, "name")
        try:
            with get_connection(db_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO company_departments (company_id, name) VALUES (?, ?)",
                    (company_id.strip(), normalized_name),
                )
                row = connection.execute(
                    "SELECT * FROM company_departments WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise CompanyOrganizationError("Подразделение с таким названием уже существует.") from exc
        if row is None:
            raise RuntimeError("Failed to load department")
        return CompanyDepartment(
            id=int(row["id"]), company_id=str(row["company_id"]), name=str(row["name"]),
            is_active=bool(row["is_active"]), created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
        )

    def provision_manager(self, db_path: Path, *, actor_user_id: int, company_id: str, department_id: int, first_name: str, last_name: str, email: str, password: str) -> ProvisionedCompanyUser:
        self._require_role(db_path, actor_user_id, company_id, "admin")
        self._require_active_department(db_path, company_id, department_id)
        return self._provision(db_path, company_id, first_name, last_name, email, password, "manager", department_id)

    def provision_employee(self, db_path: Path, *, actor_user_id: int, company_id: str, first_name: str, last_name: str, email: str, password: str) -> ProvisionedCompanyUser:
        actor = self._require_role(db_path, actor_user_id, company_id, "manager")
        department_id = actor["department_id"]
        if department_id is None:
            raise CompanyOrganizationError("У менеджера не назначено подразделение.")
        self._require_active_department(db_path, company_id, int(department_id))
        return self._provision(db_path, company_id, first_name, last_name, email, password, "student", int(department_id), actor_user_id)

    def list_managers(
        self, db_path: Path, *, actor_user_id: int, company_id: str
    ) -> tuple[CompanyManager, ...]:
        """List current and disabled managers after tenant-admin authorization."""
        self._require_role(db_path, actor_user_id, company_id, "admin")
        normalized_company_id = _required(company_id, "company_id")
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    memberships.user_id,
                    COALESCE(
                        NULLIF(TRIM(COALESCE(users.first_name, '') || ' ' ||
                                    COALESCE(users.last_name, '')), ''),
                        credentials.email
                    ) AS display_name,
                    credentials.email,
                    departments.name AS department_name,
                    memberships.is_active
                FROM company_memberships AS memberships
                JOIN users ON users.id = memberships.user_id
                JOIN user_password_credentials AS credentials
                  ON credentials.user_id = users.id
                LEFT JOIN company_member_organizations AS organization
                  ON organization.company_id = memberships.company_id
                 AND organization.user_id = memberships.user_id
                LEFT JOIN company_departments AS departments
                  ON departments.id = organization.department_id
                 AND departments.company_id = memberships.company_id
                WHERE memberships.company_id = ?
                  AND memberships.role = 'manager'
                ORDER BY memberships.is_active DESC, display_name COLLATE NOCASE
                """,
                (normalized_company_id,),
            ).fetchall()
        return tuple(
            CompanyManager(
                user_id=int(row["user_id"]),
                display_name=str(row["display_name"]),
                email=str(row["email"]),
                department_name=(
                    str(row["department_name"])
                    if row["department_name"] is not None
                    else None
                ),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        )

    def set_manager_active(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        company_id: str,
        target_user_id: int,
        is_active: bool,
        reason: str,
    ) -> None:
        """Enable or disable a manager while preserving all company data."""
        self._require_role(db_path, actor_user_id, company_id, "admin")
        normalized_company_id = _required(company_id, "company_id")
        normalized_reason = _required(reason, "reason")
        if not isinstance(is_active, bool):
            raise CompanyOrganizationError("Некорректный статус доступа.")
        try:
            membership = self._memberships.get(
                db_path, normalized_company_id, target_user_id
            )
        except ValueError as error:
            raise CompanyOrganizationError("Некорректный пользователь.") from error
        if membership is None or membership.role != "manager":
            raise CompanyOrganizationError("Менеджер не найден в этой компании.")
        if membership.is_active == is_active:
            return
        if not self._memberships.set_active(
            db_path, normalized_company_id, target_user_id, is_active
        ):
            raise RuntimeError("Не удалось изменить доступ менеджера.")
        self._platform_admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action=("company_manager.activated" if is_active else "company_manager.deactivated"),
            target_type="company_member",
            target_id=f"{normalized_company_id}:{target_user_id}",
            reason=normalized_reason,
        )

    def _provision(self, db_path: Path, company_id: str, first_name: str, last_name: str, email: str, password: str, role: str, department_id: Optional[int], manager_user_id: Optional[int] = None) -> ProvisionedCompanyUser:
        try:
            return self._provisioning.provision(
                db_path, company_id=company_id, first_name=first_name, last_name=last_name,
                email=email, password=password, role=role, department_id=department_id,
                manager_user_id=manager_user_id,
            )
        except CompanyUserProvisioningError as exc:
            raise CompanyOrganizationError(str(exc)) from exc

    @staticmethod
    def _require_role(db_path: Path, user_id: int, company_id: str, role: str):
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise CompanyOrganizationError("Некорректный пользователь.")
        normalized_company_id = _required(company_id, "company_id")
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT company_memberships.role, organization.department_id
                FROM company_memberships
                LEFT JOIN company_member_organizations AS organization
                  ON organization.company_id = company_memberships.company_id
                 AND organization.user_id = company_memberships.user_id
                WHERE company_memberships.company_id = ?
                  AND company_memberships.user_id = ?
                  AND company_memberships.is_active = 1
                """, (normalized_company_id, user_id),
            ).fetchone()
        if row is None or str(row["role"]) != role:
            raise CompanyOrganizationError("Недостаточно прав для этой операции.")
        return row

    @staticmethod
    def _require_active_department(db_path: Path, company_id: str, department_id: int) -> None:
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT id FROM company_departments WHERE id = ? AND company_id = ? AND is_active = 1",
                (department_id, _required(company_id, "company_id")),
            ).fetchone()
        if row is None:
            raise CompanyOrganizationError("Подразделение недоступно.")


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompanyOrganizationError(f"{field} must not be empty")
    return value.strip()
