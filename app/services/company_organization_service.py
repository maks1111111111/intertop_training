"""Role-bound department and team provisioning inside a company."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from app.database.db import get_connection
from app.repositories.company_department_repository import CompanyDepartment
from app.services.company_user_provisioning_service import (
    CompanyUserProvisioningError,
    CompanyUserProvisioningService,
    ProvisionedCompanyUser,
)


class CompanyOrganizationError(ValueError):
    """Raised when an organization operation violates the role hierarchy."""


class CompanyOrganizationService:
    """Apply owner/admin/manager boundaries to company setup operations."""

    def __init__(self, provisioning: Optional[CompanyUserProvisioningService] = None) -> None:
        self._provisioning = provisioning or CompanyUserProvisioningService()

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
