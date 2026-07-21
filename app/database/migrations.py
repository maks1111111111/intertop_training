import sqlite3
from typing import Dict


def _get_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> Dict[str, sqlite3.Row]:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row["name"]: row for row in rows}


def migrate_users_table(connection: sqlite3.Connection) -> None:
    columns = _get_table_columns(connection, "users")

    if "role" not in columns:
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN role TEXT NOT NULL DEFAULT 'student'
            """
        )

    if "is_active" not in columns:
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
            """
        )

    if "updated_at" not in columns:
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            """
        )


def run_migrations(connection: sqlite3.Connection) -> None:
    migrate_users_table(connection)