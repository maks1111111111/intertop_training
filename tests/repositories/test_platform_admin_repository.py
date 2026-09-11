"""Tests for explicit global platform access persistence."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.platform_admin_repository import PlatformAdminRepository


class PlatformAdminRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = PlatformAdminRepository()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user(self, *, active: bool = True) -> int:
        with get_connection(self.db_path) as connection:
            return int(
                connection.execute(
                    "INSERT INTO users (username, is_active) VALUES (?, ?)",
                    ("platform-user", 1 if active else 0),
                ).lastrowid
            )

    def test_bootstrap_creates_the_only_active_owner_and_audit_event(self) -> None:
        user_id = self._create_user()

        owner = self.repository.bootstrap_owner(self.db_path, user_id)

        self.assertEqual(owner.user_id, user_id)
        self.assertTrue(owner.is_owner)
        self.assertTrue(owner.is_active)
        self.assertEqual(
            self.repository.get_active_by_user_id(self.db_path, user_id),
            owner,
        )
        events = self.repository.list_audit_events(self.db_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor_user_id, user_id)
        self.assertEqual(events[0].action, "platform_admin.bootstrap_owner")
        self.assertEqual(events[0].target_id, str(user_id))
        self.assertEqual(events[0].reason, "bootstrap_cli")

    def test_bootstrap_is_idempotent_for_the_same_owner_without_extra_audit(self) -> None:
        user_id = self._create_user()
        self.repository.bootstrap_owner(self.db_path, user_id)

        repeated = self.repository.bootstrap_owner(self.db_path, user_id)

        self.assertEqual(repeated.user_id, user_id)
        self.assertEqual(len(self.repository.list_audit_events(self.db_path)), 1)

    def test_bootstrap_refuses_to_replace_an_existing_owner(self) -> None:
        first_user_id = self._create_user()
        second_user_id = self._create_user()
        self.repository.bootstrap_owner(self.db_path, first_user_id)

        with self.assertRaisesRegex(RuntimeError, "owner already exists"):
            self.repository.bootstrap_owner(self.db_path, second_user_id)

    def test_bootstrap_requires_an_existing_active_user(self) -> None:
        inactive_user_id = self._create_user(active=False)

        with self.assertRaisesRegex(ValueError, "active user"):
            self.repository.bootstrap_owner(self.db_path, inactive_user_id)

        self.assertIsNone(self.repository.get_by_user_id(self.db_path, inactive_user_id))

    def test_inactive_user_immediately_loses_platform_access(self) -> None:
        user_id = self._create_user()
        self.repository.bootstrap_owner(self.db_path, user_id)
        with get_connection(self.db_path) as connection:
            connection.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))

        self.assertIsNone(self.repository.get_active_by_user_id(self.db_path, user_id))

    def test_audit_events_cannot_be_changed_or_deleted(self) -> None:
        user_id = self._create_user()
        self.repository.bootstrap_owner(self.db_path, user_id)

        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("UPDATE platform_audit_events SET reason = 'changed'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("DELETE FROM platform_audit_events")


if __name__ == "__main__":
    unittest.main()
