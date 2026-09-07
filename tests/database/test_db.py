"""Tests for shared SQLite connection hardening."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import (
    SQLITE_BUSY_TIMEOUT_MS,
    get_connection,
    initialize_database,
)


class DatabaseConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_connection_applies_shared_safety_pragmas(self) -> None:
        with get_connection(self.db_path) as connection:
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]

            self.assertIs(connection.row_factory, sqlite3.Row)
            self.assertEqual(foreign_keys, 1)
            self.assertEqual(busy_timeout, SQLITE_BUSY_TIMEOUT_MS)
            self.assertEqual(synchronous, 1)

    def test_initialize_database_enables_wal_mode(self) -> None:
        initialize_database(self.db_path)

        with sqlite3.connect(self.db_path) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual(journal_mode, "wal")


if __name__ == "__main__":
    unittest.main()
