"""Tests for atomic tenant Web-user provisioning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.company_repository import CompanyRepository
from app.services.company_user_provisioning_service import (
    CompanyUserProvisioningError,
    CompanyUserProvisioningService,
)
from app.web.password_hashing_service import PasswordHashingService


class CompanyUserProvisioningServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        CompanyRepository().create(self.db_path, "alpha", "Alpha")
        self.service = CompanyUserProvisioningService()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_provisions_credential_and_membership_inside_company(self) -> None:
        user = self.service.provision(
            self.db_path, company_id="alpha", first_name="Ada", last_name="Lovelace",
            email=" Ada@example.com ", password="Strong-password-123!", role="admin",
        )
        with get_connection(self.db_path) as connection:
            membership = connection.execute("SELECT company_id, role FROM company_memberships WHERE user_id = ?", (user.user_id,)).fetchone()
            credential = connection.execute("SELECT password_hash FROM user_password_credentials WHERE user_id = ?", (user.user_id,)).fetchone()
        self.assertEqual((user.email, user.role), ("ada@example.com", "admin"))
        self.assertEqual((membership["company_id"], membership["role"]), ("alpha", "admin"))
        self.assertTrue(PasswordHashingService().verify_password("Strong-password-123!", credential["password_hash"]).valid)

    def test_rejects_short_password_without_creating_user(self) -> None:
        with self.assertRaisesRegex(CompanyUserProvisioningError, "12"):
            self.service.provision(self.db_path, company_id="alpha", first_name="Ada", last_name="", email="ada@example.com", password="short", role="admin")
        with get_connection(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
