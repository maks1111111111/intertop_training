"""Tests for verified SQLite production backups."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.database.backup import create_database_backup
from app.database.db import get_connection, initialize_database


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "data" / "training.db"
        self.backup_dir = self.root / "backups"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_user(self, username: str) -> int:
        with get_connection(self.db_path) as connection:
            return int(
                connection.execute(
                    """
                    INSERT INTO users (username, first_name, last_name)
                    VALUES (?, ?, ?)
                    """,
                    (username, "Backup", "User"),
                ).lastrowid
            )

    def test_backup_is_readable_and_contains_committed_data(self) -> None:
        user_id = self._insert_user("backup-user")

        backup_path = create_database_backup(self.db_path, self.backup_dir)

        with sqlite3.connect(backup_path) as connection:
            row = connection.execute(
                "SELECT username FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]

        self.assertEqual(row, ("backup-user",))
        self.assertEqual(integrity, "ok")

    def test_backup_includes_committed_wal_changes(self) -> None:
        with get_connection(self.db_path) as writer:
            writer.execute("PRAGMA wal_autocheckpoint = 0")
            writer.execute(
                "INSERT INTO users (username) VALUES (?)",
                ("wal-user",),
            )
            writer.commit()

            backup_path = create_database_backup(self.db_path, self.backup_dir)

        with sqlite3.connect(backup_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM users WHERE username = ?",
                ("wal-user",),
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_backup_file_is_private_and_temporary_file_is_removed(self) -> None:
        backup_path = create_database_backup(self.db_path, self.backup_dir)

        self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.backup_dir.glob("*.tmp")), [])

    def test_retention_keeps_only_newest_matching_backups(self) -> None:
        moments = iter(
            [
                datetime(2026, 9, 8, 8, minute, tzinfo=timezone.utc)
                for minute in range(3)
            ]
        )
        unrelated = self.backup_dir / "another-database-backup-old.sqlite3"
        self.backup_dir.mkdir()
        unrelated.write_bytes(b"keep")

        for _ in range(3):
            create_database_backup(
                self.db_path,
                self.backup_dir,
                keep_last=2,
                clock=lambda: next(moments),
            )

        backups = sorted(self.backup_dir.glob("training-backup-*.sqlite3"))
        self.assertEqual(len(backups), 2)
        backup_names = [path.name for path in backups]
        self.assertFalse(any("080000" in name for name in backup_names))
        self.assertTrue(any("080100" in name for name in backup_names))
        self.assertTrue(any("080200" in name for name in backup_names))
        self.assertTrue(unrelated.exists())

    def test_same_timestamp_creates_distinct_backup_names(self) -> None:
        moment = datetime(2026, 9, 8, 8, 0, tzinfo=timezone.utc)

        first = create_database_backup(
            self.db_path,
            self.backup_dir,
            clock=lambda: moment,
        )
        second = create_database_backup(
            self.db_path,
            self.backup_dir,
            clock=lambda: moment,
        )

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_missing_database_is_rejected_without_creating_output(self) -> None:
        missing_path = self.root / "missing.db"

        with self.assertRaises(FileNotFoundError):
            create_database_backup(missing_path, self.backup_dir)

        self.assertFalse(missing_path.exists())
        self.assertFalse(self.backup_dir.exists())

    def test_invalid_retention_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_database_backup(
                self.db_path,
                self.backup_dir,
                keep_last=0,
            )


if __name__ == "__main__":
    unittest.main()
