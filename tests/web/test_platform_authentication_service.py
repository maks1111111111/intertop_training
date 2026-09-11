"""Tests for global platform authentication without tenant membership."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.password_credential_repository import PasswordCredentialRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.services.platform_admin_context_service import PlatformAdminContextService
from app.web.password_hashing_service import PasswordHashingService
from app.web.platform_authentication_service import PlatformAuthenticationService


class PlatformAuthenticationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.credentials = PasswordCredentialRepository()
        self.admins = PlatformAdminRepository()
        self.passwords = PasswordHashingService()
        self.service = PlatformAuthenticationService(
            self.credentials,
            self.passwords,
            PlatformAdminContextService(self.admins),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user_with_credentials(self) -> int:
        with get_connection(self.db_path) as connection:
            user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('platform-user')"
                ).lastrowid
            )
        self.credentials.create(
            self.db_path,
            user_id=user_id,
            email="owner@example.com",
            password_hash=self.passwords.hash_password("Strong-password-123!"),
        )
        return user_id

    def test_owner_authenticates_without_any_company_or_membership(self) -> None:
        user_id = self._create_user_with_credentials()
        self.admins.bootstrap_owner(self.db_path, user_id)

        context = self.service.authenticate(
            self.db_path,
            email=" OWNER@example.com ",
            password="Strong-password-123!",
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.user_id, user_id)
        self.assertTrue(context.is_owner)

    def test_valid_tenant_credentials_do_not_imply_platform_access(self) -> None:
        self._create_user_with_credentials()

        context = self.service.authenticate(
            self.db_path,
            email="owner@example.com",
            password="Strong-password-123!",
        )

        self.assertIsNone(context)

    def test_inactive_credential_or_user_cannot_authenticate(self) -> None:
        user_id = self._create_user_with_credentials()
        self.admins.bootstrap_owner(self.db_path, user_id)
        self.credentials.set_active(self.db_path, user_id, False)
        self.assertIsNone(
            self.service.authenticate(
                self.db_path,
                email="owner@example.com",
                password="Strong-password-123!",
            )
        )

        self.credentials.set_active(self.db_path, user_id, True)
        with get_connection(self.db_path) as connection:
            connection.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        self.assertIsNone(
            self.service.authenticate(
                self.db_path,
                email="owner@example.com",
                password="Strong-password-123!",
            )
        )


if __name__ == "__main__":
    unittest.main()
