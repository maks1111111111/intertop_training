"""Tests for the tenant role hierarchy used by team management."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.department_repository import DepartmentRepository
from app.web.company_team_management_service import (
    CompanyTeamManagementError,
    CompanyTeamManagementService,
)


class _Provisioner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def provision(self, db_path: Path, **values):
        self.calls.append(values)
        return values


class CompanyTeamManagementServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "team.db"
        initialize_database(self.db_path)
        self.provisioner = _Provisioner()
        self.service = CompanyTeamManagementService(
            DepartmentRepository(), self.provisioner  # type: ignore[arg-type]
        )
        with get_connection(self.db_path) as connection:
            connection.execute("INSERT INTO companies (id, name) VALUES ('acme', 'Acme')")
            for user_id, role, department_id in ((1, "admin", None), (2, "manager", None)):
                connection.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, f"u{user_id}"))
                connection.execute(
                    "INSERT INTO company_memberships (company_id, user_id, role, department_id) VALUES ('acme', ?, ?, ?)",
                    (user_id, role, department_id),
                )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_admin_creates_department_then_manager_is_bound_to_it(self) -> None:
        department = self.service.create_department(
            self.db_path, company_id="acme", actor_user_id=1, name="Retail"
        )
        self.service.create_manager(
            self.db_path, company_id="acme", actor_user_id=1,
            department_id=department.id, first_name="Mira", last_name="",
            email="mira@example.test", password="password-long-enough",
        )
        self.assertEqual(self.provisioner.calls[0]["role"], "manager")
        self.assertEqual(self.provisioner.calls[0]["department_id"], department.id)

    def test_manager_can_create_employee_only_in_own_department(self) -> None:
        department = DepartmentRepository().create(self.db_path, "acme", "Retail")
        with get_connection(self.db_path) as connection:
            connection.execute(
                "UPDATE company_memberships SET department_id = ? WHERE company_id = 'acme' AND user_id = 2",
                (department.id,),
            )
        self.service.create_employee(
            self.db_path, company_id="acme", actor_user_id=2, first_name="Ada",
            last_name="", email="ada@example.test", password="password-long-enough",
        )
        self.assertEqual(self.provisioner.calls[0]["role"], "student")
        self.assertEqual(self.provisioner.calls[0]["department_id"], department.id)

    def test_admin_cannot_use_manager_employee_creation_path(self) -> None:
        with self.assertRaises(CompanyTeamManagementError):
            self.service.create_employee(
                self.db_path, company_id="acme", actor_user_id=1, first_name="Ada",
                last_name="", email="ada@example.test", password="password-long-enough",
            )


if __name__ == "__main__":
    unittest.main()
