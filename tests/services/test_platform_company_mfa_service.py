"""Owner-only recovery contracts for tenant administrator MFA."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.repositories.user_mfa_repository import UserMFARepository
from app.services.platform_company_mfa_service import (
    PlatformCompanyMFAError,
    PlatformCompanyMFAService,
)


class PlatformCompanyMFAServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            self.owner_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('owner')"
                ).lastrowid
            )
            self.admin_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('tenant-admin')"
                ).lastrowid
            )
            connection.execute(
                "INSERT INTO companies (id, name) VALUES ('company-a', 'A')"
            )
            connection.execute(
                """
                INSERT INTO company_memberships (company_id, user_id, role)
                VALUES ('company-a', ?, 'admin')
                """,
                (self.admin_id,),
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                ) VALUES (?, 'admin@example.com', 'hash')
                """,
                (self.admin_id,),
            )
        self.platform_admins = PlatformAdminRepository()
        self.platform_admins.bootstrap_owner(self.db_path, self.owner_id)
        self.mfa = UserMFARepository()
        self.mfa.replace_pending(
            self.db_path,
            user_id=self.admin_id,
            encrypted_secret="encrypted-secret",
        )
        self.mfa.activate(self.db_path, user_id=self.admin_id, counter=1)
        self.service = PlatformCompanyMFAService(
            self.mfa,
            self.platform_admins,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_owner_reset_is_scoped_and_audited(self) -> None:
        statuses = self.service.list_admins(self.db_path)
        self.assertEqual(len(statuses), 1)
        self.assertTrue(statuses[0].is_enrolled)

        self.service.reset(
            self.db_path,
            actor_user_id=self.owner_id,
            company_id="company-a",
            target_user_id=self.admin_id,
            reason="lost authenticator",
        )

        self.assertIsNone(self.mfa.get(self.db_path, self.admin_id))
        event = self.platform_admins.list_audit_events(self.db_path, limit=1)[0]
        self.assertEqual(event.action, "company_admin.mfa_reset")
        self.assertEqual(event.target_id, str(self.admin_id))
        self.assertIn("company=company-a", event.reason)

    def test_reset_rejects_admin_from_another_company(self) -> None:
        with self.assertRaisesRegex(
            PlatformCompanyMFAError,
            "не найден",
        ):
            self.service.reset(
                self.db_path,
                actor_user_id=self.owner_id,
                company_id="company-b",
                target_user_id=self.admin_id,
                reason="wrong tenant",
            )
        self.assertIsNotNone(self.mfa.get(self.db_path, self.admin_id))


if __name__ == "__main__":
    unittest.main()
