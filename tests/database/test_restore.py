"""Tests for rollback-safe SQLite restore operations."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database.backup import create_database_backup
from app.database.db import get_connection, initialize_database
from app.database.restore import DatabaseRestoreError, restore_database_backup


class DatabaseRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "data" / "training.db"
        self.backup_dir = self.root / "backups"
        self.safety_dir = self.root / "safety"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_user(self, username: str) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO users (username) VALUES (?)",
                (username,),
            )

    @staticmethod
    def _usernames(db_path: Path) -> list[str]:
        with sqlite3.connect(db_path) as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT username FROM users ORDER BY username"
                ).fetchall()
            ]

    def test_restore_replaces_database_and_preserves_safety_backup(self) -> None:
        self._insert_user("before-backup")
        backup_path = create_database_backup(self.db_path, self.backup_dir)
        self._insert_user("after-backup")

        result = restore_database_backup(
            backup_path,
            self.db_path,
            self.safety_dir,
        )

        self.assertEqual(self._usernames(self.db_path), ["before-backup"])
        self.assertIsNotNone(result.safety_backup_path)
        assert result.safety_backup_path is not None
        self.assertEqual(
            self._usernames(result.safety_backup_path),
            ["after-backup", "before-backup"],
        )
        self.assertEqual(self.db_path.stat().st_mode & 0o777, 0o600)

    def test_restore_to_missing_database_does_not_create_safety_backup(self) -> None:
        self._insert_user("restored-user")
        backup_path = create_database_backup(self.db_path, self.backup_dir)
        restored_path = self.root / "restored" / "training.db"

        result = restore_database_backup(
            backup_path,
            restored_path,
            self.safety_dir,
        )

        self.assertEqual(self._usernames(restored_path), ["restored-user"])
        self.assertIsNone(result.safety_backup_path)
        self.assertFalse(self.safety_dir.exists())

    def test_corrupt_backup_is_rejected_before_current_database_changes(self) -> None:
        self._insert_user("current-user")
        corrupt_backup = self.root / "corrupt.sqlite3"
        corrupt_backup.write_bytes(b"not a sqlite database")

        with self.assertRaises(DatabaseRestoreError):
            restore_database_backup(
                corrupt_backup,
                self.db_path,
                self.safety_dir,
            )

        self.assertEqual(self._usernames(self.db_path), ["current-user"])
        self.assertFalse(self.safety_dir.exists())

    def test_backup_without_application_schema_is_rejected(self) -> None:
        invalid_backup = self.root / "empty.sqlite3"
        with sqlite3.connect(invalid_backup):
            pass

        with self.assertRaisesRegex(DatabaseRestoreError, "users table"):
            restore_database_backup(
                invalid_backup,
                self.db_path,
                self.safety_dir,
            )

    def test_restore_refuses_database_with_active_write_transaction(self) -> None:
        backup_path = create_database_backup(self.db_path, self.backup_dir)

        with get_connection(self.db_path) as active_connection:
            active_connection.execute("BEGIN IMMEDIATE")
            active_connection.execute(
                "INSERT INTO users (username) VALUES (?)",
                ("active-user",),
            )
            self.assertTrue(Path(f"{self.db_path}-wal").exists())

            with self.assertRaisesRegex(DatabaseRestoreError, "stop the application"):
                restore_database_backup(
                    backup_path,
                    self.db_path,
                    self.safety_dir,
                )
            active_connection.rollback()

        self.assertEqual(self._usernames(self.db_path), [])
        self.assertFalse(self.safety_dir.exists())

    def test_restore_rejects_using_database_as_its_own_backup(self) -> None:
        with self.assertRaisesRegex(DatabaseRestoreError, "paths must differ"):
            restore_database_backup(
                self.db_path,
                self.db_path,
                self.safety_dir,
            )

    def test_replace_failure_keeps_current_database_and_removes_temporary_file(
        self,
    ) -> None:
        self._insert_user("backup-version")
        backup_path = create_database_backup(self.db_path, self.backup_dir)
        self._insert_user("current-version")

        with patch(
            "app.database.restore._replace_database_file",
            side_effect=OSError("disk failure"),
        ):
            with self.assertRaises(OSError):
                restore_database_backup(
                    backup_path,
                    self.db_path,
                    self.safety_dir,
                )

        self.assertEqual(
            self._usernames(self.db_path),
            ["backup-version", "current-version"],
        )
        self.assertEqual(list(self.db_path.parent.glob("*.restore.tmp")), [])
        self.assertEqual(len(list(self.safety_dir.glob("*.sqlite3"))), 1)


if __name__ == "__main__":
    unittest.main()
