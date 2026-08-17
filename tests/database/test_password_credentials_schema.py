"""Schema and migration tests for password credentials."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database


class PasswordCredentialsSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user(self, connection: sqlite3.Connection) -> int:
        cursor = connection.execute(
            "INSERT INTO users (username) VALUES (?)",
            ("web-user",),
        )
        return int(cursor.lastrowid)

    def test_table_exists_on_fresh_database(self) -> None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'user_password_credentials'
                """
            ).fetchone()

        self.assertIsNotNone(row)

    def test_expected_columns_exist(self) -> None:
        with get_connection(self.db_path) as connection:
            columns = [
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(user_password_credentials)"
                ).fetchall()
            ]

        self.assertEqual(
            columns,
            [
                "id",
                "user_id",
                "email",
                "password_hash",
                "is_active",
                "created_at",
                "updated_at",
            ],
        )

    def test_multiple_users_can_have_distinct_credentials(self) -> None:
        with get_connection(self.db_path) as connection:
            first = self._create_user(connection)
            second = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES (?)",
                    ("web-user-2",),
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                )
                VALUES (?, ?, ?)
                """,
                (first, "first@example.com", "hash-one"),
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                )
                VALUES (?, ?, ?)
                """,
                (second, "second@example.com", "hash-two"),
            )

            count = connection.execute(
                "SELECT COUNT(*) FROM user_password_credentials"
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_email_uniqueness_is_case_insensitive(self) -> None:
        with get_connection(self.db_path) as connection:
            first = self._create_user(connection)
            second = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES (?)",
                    ("second",),
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                )
                VALUES (?, ?, ?)
                """,
                (first, "User@Example.com", "hash-one"),
            )

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO user_password_credentials (
                        user_id, email, password_hash
                    )
                    VALUES (?, ?, ?)
                    """,
                    (second, "user@example.com", "hash-two"),
                )

    def test_one_credential_record_per_user(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = self._create_user(connection)
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                )
                VALUES (?, ?, ?)
                """,
                (user_id, "first@example.com", "hash-one"),
            )

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO user_password_credentials (
                        user_id, email, password_hash
                    )
                    VALUES (?, ?, ?)
                    """,
                    (user_id, "second@example.com", "hash-two"),
                )

    def test_unknown_user_is_rejected(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO user_password_credentials (
                        user_id, email, password_hash
                    )
                    VALUES (?, ?, ?)
                    """,
                    (999999, "missing@example.com", "hash"),
                )

    def test_deleting_user_cascades_credentials(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = self._create_user(connection)
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                )
                VALUES (?, ?, ?)
                """,
                (user_id, "user@example.com", "hash"),
            )
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM user_password_credentials
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_initialize_database_is_idempotent(self) -> None:
        initialize_database(self.db_path)
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'user_password_credentials'
                """
            ).fetchone()

        self.assertIsNotNone(row)

    def test_legacy_database_gets_credentials_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
            connection.close()

            initialize_database(db_path)

            with get_connection(db_path) as migrated:
                row = migrated.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name = 'user_password_credentials'
                    """
                ).fetchone()

        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
