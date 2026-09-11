"""Tests for audited owner-only company lifecycle operations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.company_repository import CompanyRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.services.platform_company_service import (
    PlatformCompanyError,
    PlatformCompanyService,
)


class PlatformCompanyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.admins = PlatformAdminRepository()
        self.companies = CompanyRepository()
        self.service = PlatformCompanyService(self.companies, self.admins)
        self.owner_id = self._create_user("owner")
        self.admins.bootstrap_owner(self.db_path, self.owner_id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user(self, username: str) -> int:
        with get_connection(self.db_path) as connection:
            return int(
                connection.execute(
                    "INSERT INTO users (username) VALUES (?)",
                    (username,),
                ).lastrowid
            )

    def test_create_company_normalizes_id_and_audits_reason(self) -> None:
        company = self.service.create_company(
            self.db_path,
            actor_user_id=self.owner_id,
            company_id="  north-shop ",
            name="North Shop",
            reason="Initial customer provisioning",
        )

        self.assertEqual(company.id, "north-shop")
        event = self.admins.list_audit_events(self.db_path)[0]
        self.assertEqual(event.action, "company.created")
        self.assertEqual(event.target_id, "north-shop")
        self.assertEqual(event.reason, "Initial customer provisioning")

    def test_state_change_requires_reason_and_writes_audit_event(self) -> None:
        self.companies.create(self.db_path, "north-shop", "North Shop")

        with self.assertRaisesRegex(PlatformCompanyError, "reason is required"):
            self.service.set_company_active(
                self.db_path,
                actor_user_id=self.owner_id,
                company_id="north-shop",
                is_active=False,
                reason=" ",
            )

        company = self.service.set_company_active(
            self.db_path,
            actor_user_id=self.owner_id,
            company_id="north-shop",
            is_active=False,
            reason="Contract ended",
        )
        self.assertFalse(company.is_active)
        event = self.admins.list_audit_events(self.db_path)[0]
        self.assertEqual(event.action, "company.deactivated")
        self.assertEqual(event.reason, "Contract ended")

    def test_non_owner_cannot_mutate_company_lifecycle(self) -> None:
        non_owner_id = self._create_user("platform-admin")
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO platform_admins (user_id) VALUES (?)",
                (non_owner_id,),
            )

        with self.assertRaisesRegex(PlatformCompanyError, "owner access"):
            self.service.create_company(
                self.db_path,
                actor_user_id=non_owner_id,
                company_id="north-shop",
                name="North Shop",
                reason="Unauthorized test",
            )

    def test_rejects_invalid_company_id(self) -> None:
        with self.assertRaisesRegex(PlatformCompanyError, "lowercase"):
            self.service.create_company(
                self.db_path,
                actor_user_id=self.owner_id,
                company_id="North Shop",
                name="North Shop",
                reason="Initial customer provisioning",
            )


if __name__ == "__main__":
    unittest.main()
