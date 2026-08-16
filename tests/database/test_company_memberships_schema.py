"""Tests for companies and company_memberships table schema and migration."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.migrations import migrate_companies_table

COMPANIES_COLUMNS = (
    "id",
    "name",
    "is_active",
    "created_at",
    "updated_at",
)

MEMBERSHIPS_COLUMNS = (
    "id",
    "company_id",
    "user_id",
    "role",
    "is_active",
    "created_at",
    "updated_at",
)

EXPECTED_MEMBERSHIP_INDEXES = (
    "idx_company_memberships_company_id",
    "idx_company_memberships_user_id",
    "idx_company_memberships_company_role",
)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row[1] for row in rows]


def _index_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA index_list({table_name})").fetchall()
    return [row[1] for row in rows]


def _insert_company(
    connection: sqlite3.Connection,
    *,
    company_id: str = "company-a",
    name: str = "Company A",
    is_active: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO companies (id, name, is_active)
        VALUES (?, ?, ?)
        """,
        (company_id, name, is_active),
    )


def _insert_user(
    connection: sqlite3.Connection,
    *,
    telegram_id: int = 1001,
    username: str = "user1",
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        """,
        (telegram_id, username, "First", "Last"),
    )
    return int(cursor.lastrowid)


def _insert_membership(
    connection: sqlite3.Connection,
    *,
    company_id: str,
    user_id: int,
    role: str = "student",
    is_active: int = 1,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO company_memberships (company_id, user_id, role, is_active)
        VALUES (?, ?, ?, ?)
        """,
        (company_id, user_id, role, is_active),
    )
    return int(cursor.lastrowid)


class CompanyMembershipsSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_initialize_database_creates_both_tables(self) -> None:
        with get_connection(self.db_path) as connection:
            self.assertTrue(_table_exists(connection, "companies"))
            self.assertTrue(_table_exists(connection, "company_memberships"))

    def test_companies_table_contains_expected_columns(self) -> None:
        with get_connection(self.db_path) as connection:
            columns = _column_names(connection, "companies")

        self.assertEqual(columns, list(COMPANIES_COLUMNS))

    def test_memberships_table_contains_expected_columns(self) -> None:
        with get_connection(self.db_path) as connection:
            columns = _column_names(connection, "company_memberships")

        self.assertEqual(columns, list(MEMBERSHIPS_COLUMNS))

    def test_minimal_company_insert_works(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection, company_id="intertop", name="Intertop")
            connection.commit()
            row = connection.execute(
                "SELECT id, name, is_active FROM companies WHERE id = ?",
                ("intertop",),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "intertop")
        self.assertEqual(row["name"], "Intertop")
        self.assertEqual(row["is_active"], 1)

    def test_membership_defaults_to_student_role_and_active(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_id = _insert_user(connection)
            membership_id = _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_id,
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT role, is_active
                FROM company_memberships
                WHERE id = ?
                """,
                (membership_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "student")
        self.assertEqual(row["is_active"], 1)

    def test_roles_student_manager_admin_are_accepted(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection, company_id="company-a", name="A")
            _insert_company(connection, company_id="company-b", name="B")
            _insert_company(connection, company_id="company-c", name="C")
            user_student = _insert_user(connection, telegram_id=2001, username="s")
            user_manager = _insert_user(connection, telegram_id=2002, username="m")
            user_admin = _insert_user(connection, telegram_id=2003, username="a")
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_student,
                role="student",
            )
            _insert_membership(
                connection,
                company_id="company-b",
                user_id=user_manager,
                role="manager",
            )
            _insert_membership(
                connection,
                company_id="company-c",
                user_id=user_admin,
                role="admin",
            )
            connection.commit()
            roles = [
                row[0]
                for row in connection.execute(
                    "SELECT role FROM company_memberships ORDER BY id"
                ).fetchall()
            ]

        self.assertEqual(roles, ["student", "manager", "admin"])

    def test_unsupported_role_is_rejected(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_id = _insert_user(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_membership(
                    connection,
                    company_id="company-a",
                    user_id=user_id,
                    role="superuser",
                )

    def test_is_active_only_accepts_zero_or_one(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_id = _insert_user(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_membership(
                    connection,
                    company_id="company-a",
                    user_id=user_id,
                    is_active=2,
                )

    def test_duplicate_membership_for_same_company_user_is_rejected(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_id = _insert_user(connection)
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_id,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_membership(
                    connection,
                    company_id="company-a",
                    user_id=user_id,
                )

    def test_same_user_can_belong_to_different_companies(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection, company_id="company-a", name="A")
            _insert_company(connection, company_id="company-b", name="B")
            user_id = _insert_user(connection)
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_id,
            )
            _insert_membership(
                connection,
                company_id="company-b",
                user_id=user_id,
            )
            connection.commit()
            count = connection.execute(
                "SELECT COUNT(*) FROM company_memberships WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_same_company_can_contain_different_users(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_a = _insert_user(connection, telegram_id=3001, username="a")
            user_b = _insert_user(connection, telegram_id=3002, username="b")
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_a,
            )
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_b,
            )
            connection.commit()
            count = connection.execute(
                "SELECT COUNT(*) FROM company_memberships WHERE company_id = ?",
                ("company-a",),
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_unknown_company_foreign_key_is_rejected(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = _insert_user(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_membership(
                    connection,
                    company_id="missing-company",
                    user_id=user_id,
                )

    def test_unknown_user_foreign_key_is_rejected(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_membership(
                    connection,
                    company_id="company-a",
                    user_id=99999,
                )

    def test_deleting_company_cascades_memberships(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_id = _insert_user(connection)
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_id,
            )
            connection.commit()
            connection.execute(
                "DELETE FROM companies WHERE id = ?",
                ("company-a",),
            )
            connection.commit()
            count = connection.execute(
                "SELECT COUNT(*) FROM company_memberships"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_deleting_user_cascades_memberships(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection)
            user_id = _insert_user(connection)
            _insert_membership(
                connection,
                company_id="company-a",
                user_id=user_id,
            )
            connection.commit()
            connection.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            )
            connection.commit()
            count = connection.execute(
                "SELECT COUNT(*) FROM company_memberships"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_expected_indexes_exist(self) -> None:
        with get_connection(self.db_path) as connection:
            index_names = _index_names(connection, "company_memberships")

        for expected_name in EXPECTED_MEMBERSHIP_INDEXES:
            self.assertIn(expected_name, index_names)

    def test_initialize_database_is_idempotent_and_preserves_rows(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_company(connection, company_id="persist-co", name="Persist Co")
            user_id = _insert_user(connection, telegram_id=4001, username="persist")
            _insert_membership(
                connection,
                company_id="persist-co",
                user_id=user_id,
                role="manager",
            )
            connection.commit()

        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            company_count = connection.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0]
            membership_count = connection.execute(
                "SELECT COUNT(*) FROM company_memberships"
            ).fetchone()[0]
            role = connection.execute(
                """
                SELECT role
                FROM company_memberships
                WHERE company_id = ? AND user_id = ?
                """,
                ("persist-co", user_id),
            ).fetchone()[0]

        self.assertEqual(company_count, 1)
        self.assertEqual(membership_count, 1)
        self.assertEqual(role, "manager")

    def test_legacy_database_with_users_is_upgraded_without_losing_user(self) -> None:
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
                """
            )
            connection.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                """,
                (4242, "legacy", "Legacy", "User"),
            )
            connection.commit()
            connection.close()

            initialize_database(db_path)

            with get_connection(db_path) as connection:
                self.assertTrue(_table_exists(connection, "companies"))
                self.assertTrue(_table_exists(connection, "company_memberships"))
                for expected_name in EXPECTED_MEMBERSHIP_INDEXES:
                    self.assertIn(
                        expected_name,
                        _index_names(connection, "company_memberships"),
                    )
                user_count = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE telegram_id = ?",
                    (4242,),
                ).fetchone()[0]

        self.assertEqual(user_count, 1)

    def test_migration_is_idempotent_and_adds_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-companies.db"
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

                CREATE TABLE companies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE company_memberships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_id, user_id),
                    FOREIGN KEY (company_id)
                        REFERENCES companies(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    CHECK (role IN ('student', 'manager', 'admin')),
                    CHECK (is_active IN (0, 1))
                );
                """
            )
            _insert_company(connection, company_id="legacy-co", name="Legacy Co")
            user_id = _insert_user(connection, telegram_id=5001, username="legacy")
            membership_id = _insert_membership(
                connection,
                company_id="legacy-co",
                user_id=user_id,
                role="admin",
            )
            connection.commit()

            named_indexes = [
                name
                for name in _index_names(connection, "company_memberships")
                if not name.startswith("sqlite_autoindex_")
            ]
            self.assertEqual(named_indexes, [])

            migrate_companies_table(connection)
            connection.commit()

            index_names = _index_names(connection, "company_memberships")
            for expected_name in EXPECTED_MEMBERSHIP_INDEXES:
                self.assertIn(expected_name, index_names)

            row = connection.execute(
                """
                SELECT company_id, user_id, role
                FROM company_memberships
                WHERE id = ?
                """,
                (membership_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "legacy-co")
            self.assertEqual(row[1], user_id)
            self.assertEqual(row[2], "admin")

            migrate_companies_table(connection)
            connection.commit()

            for expected_name in EXPECTED_MEMBERSHIP_INDEXES:
                self.assertIn(
                    expected_name,
                    _index_names(connection, "company_memberships"),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM company_memberships"
            ).fetchone()[0]
            connection.close()

        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
