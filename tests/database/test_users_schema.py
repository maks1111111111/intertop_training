"""Schema and migration tests for channel-agnostic users."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.migrations import migrate_users_table


class UsersSchemaTests(unittest.TestCase):
    """Verify Telegram identity is optional without weakening uniqueness."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fresh_database_allows_null_telegram_id(self) -> None:
        with get_connection(self.db_path) as connection:
            telegram_column = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }["telegram_id"]

        self.assertEqual(int(telegram_column["notnull"]), 0)

    def test_multiple_users_without_telegram_id_are_allowed(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO users (telegram_id, username) VALUES (NULL, ?)",
                ("web-a",),
            )
            connection.execute(
                "INSERT INTO users (telegram_id, username) VALUES (NULL, ?)",
                ("web-b",),
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM users WHERE telegram_id IS NULL"
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_real_telegram_id_remains_unique(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
                (1001, "first"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
                    (1001, "duplicate"),
                )

    def test_legacy_database_migration_preserves_ids_and_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            connection = sqlite3.connect(db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'assigned',
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(user_id, course_id),
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (course_id)
                        REFERENCES courses(id)
                        ON DELETE CASCADE
                );
                """
            )
            connection.execute(
                """
                INSERT INTO users (
                    id, telegram_id, username, first_name, last_name, role
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (42, 4242, "legacy", "Legacy", "User", "admin"),
            )
            connection.execute(
                """
                INSERT INTO courses (id, slug, title, status)
                VALUES (?, ?, ?, ?)
                """,
                (7, "legacy-course", "Legacy Course", "published"),
            )
            connection.execute(
                """
                INSERT INTO enrollments (user_id, course_id)
                VALUES (?, ?)
                """,
                (42, 7),
            )
            connection.commit()
            connection.close()

            initialize_database(db_path)

            with get_connection(db_path) as migrated:
                user = migrated.execute(
                    """
                    SELECT id, telegram_id, username, role
                    FROM users
                    WHERE id = ?
                    """,
                    (42,),
                ).fetchone()
                enrollment = migrated.execute(
                    """
                    SELECT user_id, course_id
                    FROM enrollments
                    WHERE user_id = ?
                    """,
                    (42,),
                ).fetchone()
                violations = migrated.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                telegram_column = {
                    row["name"]: row
                    for row in migrated.execute(
                        "PRAGMA table_info(users)"
                    ).fetchall()
                }["telegram_id"]

        self.assertIsNotNone(user)
        self.assertEqual(user["id"], 42)
        self.assertEqual(user["telegram_id"], 4242)
        self.assertEqual(user["username"], "legacy")
        self.assertEqual(user["role"], "admin")
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment["user_id"], 42)
        self.assertEqual(enrollment["course_id"], 7)
        self.assertEqual(violations, [])
        self.assertEqual(int(telegram_column["notnull"]), 0)

    def test_legacy_minimal_users_table_migrates_with_defaults(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO users (
                id, telegram_id, username, first_name, last_name
            )
            VALUES (9, 9009, 'legacy-minimal', 'Legacy', 'Minimal');
            """
        )

        migrate_users_table(connection)

        row = connection.execute(
            """
            SELECT id, telegram_id, username, role, is_active, updated_at
            FROM users
            WHERE id = 9
            """
        ).fetchone()
        telegram_column = {
            item["name"]: item
            for item in connection.execute("PRAGMA table_info(users)").fetchall()
        }["telegram_id"]

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], 9)
        self.assertEqual(row["telegram_id"], 9009)
        self.assertEqual(row["role"], "student")
        self.assertEqual(row["is_active"], 1)
        self.assertIsNotNone(row["updated_at"])
        self.assertEqual(int(telegram_column["notnull"]), 0)
        connection.close()

    def test_legacy_null_updated_at_is_normalized_during_rebuild(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT NOT NULL DEFAULT 'student',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO users (
                id,
                telegram_id,
                username,
                role,
                is_active,
                created_at,
                updated_at
            )
            VALUES (
                17,
                1717,
                'legacy-null-updated',
                'student',
                1,
                CURRENT_TIMESTAMP,
                NULL
            );
            """
        )

        migrate_users_table(connection)

        row = connection.execute(
            """
            SELECT id, telegram_id, updated_at
            FROM users
            WHERE id = 17
            """
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], 17)
        self.assertEqual(row["telegram_id"], 1717)
        self.assertIsNotNone(row["updated_at"])
        connection.close()

    def test_users_migration_is_idempotent(self) -> None:
        with get_connection(self.db_path) as connection:
            migrate_users_table(connection)
            migrate_users_table(connection)

            columns = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            indexes = {
                row["name"]
                for row in connection.execute("PRAGMA index_list(users)").fetchall()
            }

        self.assertEqual(int(columns["telegram_id"]["notnull"]), 0)
        self.assertIn("idx_users_telegram_id", indexes)


if __name__ == "__main__":
    unittest.main()
