"""Tests for fresh-password confirmation of sensitive owner operations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.password_credential_repository import PasswordCredentialRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.services.platform_owner_confirmation_service import (
    PlatformOwnerConfirmationService,
)
from app.web.password_hashing_service import PasswordHashingService


class PlatformOwnerConfirmationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            self.owner_id = int(connection.execute("INSERT INTO users (username) VALUES ('owner')").lastrowid)
            self.other_id = int(connection.execute("INSERT INTO users (username) VALUES ('other')").lastrowid)
        self.passwords = PasswordHashingService()
        self.credentials = PasswordCredentialRepository()
        self.credentials.create(self.db_path, user_id=self.owner_id, email="owner@example.com", password_hash=self.passwords.hash_password("Strong-password-123!"))
        self.admins = PlatformAdminRepository()
        self.admins.bootstrap_owner(self.db_path, self.owner_id)
        self.service = PlatformOwnerConfirmationService(self.credentials, self.admins, self.passwords)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_only_current_owner_password_confirms(self) -> None:
        self.assertTrue(self.service.confirm(self.db_path, owner_user_id=self.owner_id, password="Strong-password-123!"))
        self.assertFalse(self.service.confirm(self.db_path, owner_user_id=self.owner_id, password="wrong"))
        self.assertFalse(self.service.confirm(self.db_path, owner_user_id=self.other_id, password="Strong-password-123!"))


if __name__ == "__main__":
    unittest.main()
