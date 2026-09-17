"""Role-safe department and employee provisioning for tenant administrators."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database.db import get_connection
from app.repositories.department_repository import Department, DepartmentRepository
from app.services.company_user_provisioning_service import (
    CompanyUserProvisioningError,
    CompanyUserProvisioningService,
    ProvisionedCompanyUser,
)


class CompanyTeamManagementError(ValueError):
    """A requested team-management operation is not permitted or valid."""


@dataclass(frozen=True)
class CompanyTeamManagementService:
    departments: DepartmentRepository
    provisioner: CompanyUserProvisioningService

    def create_department(self, db_path: Path, *, company_id: str, actor_user_id: int, name: str) -> Department:
        self._require_role(db_path, company_id, actor_user_id, "admin")
        try:
            return self.departments.create(db_path, company_id, name)
        except sqlite3.IntegrityError as exc:
            raise CompanyTeamManagementError("Подразделение с таким названием уже существует.") from exc
        except ValueError as exc:
            raise CompanyTeamManagementError("Укажите название подразделения.") from exc

    def create_manager(self, db_path: Path, *, company_id: str, actor_user_id: int, department_id: int, first_name: str, last_name: str, email: str, password: str) -> ProvisionedCompanyUser:
        self._require_role(db_path, company_id, actor_user_id, "admin")
        return self._provision(
            db_path, company_id=company_id, role="manager", department_id=department_id,
            first_name=first_name, last_name=last_name, email=email, password=password,
        )

    def create_employee(self, db_path: Path, *, company_id: str, actor_user_id: int, first_name: str, last_name: str, email: str, password: str) -> ProvisionedCompanyUser:
        membership = self._require_role(db_path, company_id, actor_user_id, "manager")
        if membership["department_id"] is None:
            raise CompanyTeamManagementError("Менеджеру не назначено подразделение.")
        return self._provision(
            db_path, company_id=company_id, role="student",
            department_id=int(membership["department_id"]), first_name=first_name,
            last_name=last_name, email=email, password=password,
        )

    def _provision(self, db_path: Path, **values) -> ProvisionedCompanyUser:
        try:
            return self.provisioner.provision(db_path, **values)
        except CompanyUserProvisioningError as exc:
            raise CompanyTeamManagementError(str(exc)) from exc

    @staticmethod
    def _require_role(db_path: Path, company_id: str, user_id: int, role: str):
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT department_id FROM company_memberships
                WHERE company_id = ? AND user_id = ? AND role = ? AND is_active = 1
                """,
                (company_id.strip(), user_id, role),
            ).fetchone()
        if row is None:
            raise CompanyTeamManagementError("Недостаточно прав для управления командой.")
        return row
