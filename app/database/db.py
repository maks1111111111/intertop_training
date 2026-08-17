import sqlite3
from pathlib import Path
from typing import Optional

from app.database.migrations import run_migrations
from app.database.schema import create_tables
def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database(db_path: Path) -> None:
    with get_connection(db_path) as connection:
        create_tables(connection)
        run_migrations(connection)

def upsert_telegram_user(
    db_path: Path,
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name,
                last_name
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                telegram_id,
                username,
                first_name,
                last_name,
            ),
        )



def get_user_by_id(
    db_path: Path,
    user_id: int,
) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()


def get_user_by_telegram_id(
    db_path: Path,
    telegram_id: int,
) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        ).fetchone()
