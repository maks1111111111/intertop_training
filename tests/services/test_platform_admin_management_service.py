"""Tests for owner-controlled platform-admin grants and revocations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.services.platform_admin_management_service import (
    PlatformAdminManagementError,
    PlatformAdminManagementService,
)


class PlatformAdminManagementServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = PlatformAdminRepository()
        self.service = PlatformAdminManagementService(self.repository)
        self.owner_id = self._create_user("owner")
        self.target_id = self._create_user("target")
        self.repository.bootstrap_owner(self.db_path, self.owner_id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user(self, username: str) -> int:
        with get_connection(self.db_path) as connection:
            return int(connection.execute("INSERT INTO users (username) VALUES (?)", (username,)).lastrowid)

    def test_owner_grants_and_revokes_with_audit(self) -> None:
        granted = self.service.grant(self.db_path, actor_user_id=self.owner_id, target_user_id=self.target_id, reason="On-call coverage")
        self.assertTrue(granted.is_active)
        self.assertFalse(granted.is_owner)
        self.service.revoke(self.db_path, actor_user_id=self.owner_id, target_user_id=self.target_id, reason="On-call rotation ended")
        self.assertIsNone(self.repository.get_active_by_user_id(self.db_path, self.target_id))
        self.assertEqual([event.action for event in self.repository.list_audit_events(self.db_path)[:2]], ["platform_admin.revoked", "platform_admin.granted"])

    def test_non_owner_cannot_grant_access(self) -> None:
        with self.assertRaisesRegex(PlatformAdminManagementError, "owner access"):
            self.service.grant(self.db_path, actor_user_id=self.target_id, target_user_id=self.target_id, reason="Unauthorized")

    def test_owner_cannot_be_revoked(self) -> None:
        with self.assertRaisesRegex(PlatformAdminManagementError, "owner cannot be revoked"):
            self.service.revoke(self.db_path, actor_user_id=self.owner_id, target_user_id=self.owner_id, reason="Invalid")


if __name__ == "__main__":
    unittest.main()
