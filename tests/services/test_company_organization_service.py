"""Tests for company department role boundaries."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.company_repository import CompanyRepository
from app.services.company_organization_service import (
    CompanyOrganizationError,
    CompanyOrganizationService,
)
from app.services.company_user_provisioning_service import CompanyUserProvisioningService
from app.repositories.company_team_repository import CompanyTeamRepository
from app.web.manager_team_service import ManagerTeamService


class CompanyOrganizationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        CompanyRepository().create(self.db_path, "alpha", "Alpha")
        self.provisioning = CompanyUserProvisioningService()
        self.service = CompanyOrganizationService(self.provisioning)
        self.admin = self.provisioning.provision(
            self.db_path, company_id="alpha", first_name="Ada", last_name="Admin",
            email="admin@example.com", password="Strong-password-123!", role="admin",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_admin_creates_department_and_manager_then_manager_creates_employee(self) -> None:
        department = self.service.create_department(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha", name="Sales"
        )
        manager = self.service.provision_manager(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha",
            department_id=department.id, first_name="Mira", last_name="Manager",
            email="manager@example.com", password="Strong-password-123!",
        )
        employee = self.service.provision_employee(
            self.db_path, actor_user_id=manager.user_id, company_id="alpha",
            first_name="Eli", last_name="Employee", email="employee@example.com",
            password="Strong-password-123!",
        )
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT membership.role, organization.department_id, organization.manager_user_id
                FROM company_memberships AS membership
                JOIN company_member_organizations AS organization
                  ON organization.company_id = membership.company_id
                 AND organization.user_id = membership.user_id
                WHERE membership.user_id = ?
                """,
                (employee.user_id,),
            ).fetchone()
        self.assertEqual((row["role"], row["department_id"], row["manager_user_id"]), ("student", department.id, manager.user_id))

    def test_manager_cannot_create_department_or_manager(self) -> None:
        department = self.service.create_department(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha", name="Sales"
        )
        manager = self.service.provision_manager(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha",
            department_id=department.id, first_name="Mira", last_name="Manager",
            email="manager@example.com", password="Strong-password-123!",
        )
        with self.assertRaises(CompanyOrganizationError):
            self.service.create_department(
                self.db_path, actor_user_id=manager.user_id, company_id="alpha", name="Warehouse"
            )
        with self.assertRaises(CompanyOrganizationError):
            self.service.provision_manager(
                self.db_path, actor_user_id=manager.user_id, company_id="alpha",
                department_id=department.id, first_name="Other", last_name="Manager",
                email="other@example.com", password="Strong-password-123!",
            )

    def test_department_scoped_team_hides_other_department(self) -> None:
        sales = self.service.create_department(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha", name="Sales"
        )
        warehouse = self.service.create_department(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha", name="Warehouse"
        )
        sales_manager = self.service.provision_manager(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha",
            department_id=sales.id, first_name="Mira", last_name="Sales",
            email="sales-manager@example.com", password="Strong-password-123!",
        )
        other_manager = self.service.provision_manager(
            self.db_path, actor_user_id=self.admin.user_id, company_id="alpha",
            department_id=warehouse.id, first_name="Wally", last_name="Warehouse",
            email="warehouse-manager@example.com", password="Strong-password-123!",
        )
        self.service.provision_employee(
            self.db_path, actor_user_id=sales_manager.user_id, company_id="alpha",
            first_name="Eli", last_name="Sales", email="sales@example.com",
            password="Strong-password-123!",
        )
        self.service.provision_employee(
            self.db_path, actor_user_id=other_manager.user_id, company_id="alpha",
            first_name="Wes", last_name="Warehouse", email="warehouse@example.com",
            password="Strong-password-123!",
        )
        members = ManagerTeamService(CompanyTeamRepository(), self.db_path).get_team(
            "alpha", sales.id
        )
        self.assertEqual({member.email if hasattr(member, "email") else member.display_name for member in members}, {"Mira Sales", "Eli Sales"})


if __name__ == "__main__":
    unittest.main()
