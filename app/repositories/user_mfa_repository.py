"""Persistence for encrypted per-user authenticator credentials."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class UserMFACredential:
    user_id: int
    encrypted_secret: str
    is_active: bool
    last_used_counter: Optional[int]
    created_at: str
    updated_at: str


def _to_credential(row: sqlite3.Row) -> UserMFACredential:
    raw_counter = row["last_used_counter"]
    return UserMFACredential(
        user_id=int(row["user_id"]),
        encrypted_secret=str(row["encrypted_secret"]),
        is_active=bool(row["is_active"]),
        last_used_counter=(int(raw_counter) if raw_counter is not None else None),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class UserMFARepository:
    """Store encrypted secrets and atomically reject replayed TOTP counters."""

    def get(self, db_path: Path, user_id: int) -> Optional[UserMFACredential]:
        normalized_user_id = _user_id(user_id)
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT * FROM user_mfa_credentials WHERE user_id = ?",
                (normalized_user_id,),
            ).fetchone()
        return _to_credential(row) if row is not None else None

    def replace_pending(
        self,
        db_path: Path,
        *,
        user_id: int,
        encrypted_secret: str,
    ) -> UserMFACredential:
        normalized_user_id = _user_id(user_id)
        normalized_secret = _encrypted_secret(encrypted_secret)
        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO user_mfa_credentials (
                    user_id, encrypted_secret, is_active, last_used_counter
                ) VALUES (?, ?, 0, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    encrypted_secret = excluded.encrypted_secret,
                    is_active = 0,
                    last_used_counter = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized_user_id, normalized_secret),
            )
            row = connection.execute(
                "SELECT * FROM user_mfa_credentials WHERE user_id = ?",
                (normalized_user_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to store pending MFA credential")
        return _to_credential(row)

    def activate(
        self,
        db_path: Path,
        *,
        user_id: int,
        counter: int,
    ) -> bool:
        normalized_user_id = _user_id(user_id)
        normalized_counter = _counter(counter)
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE user_mfa_credentials
                SET is_active = 1,
                    last_used_counter = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND is_active = 0
                """,
                (normalized_counter, normalized_user_id),
            )
        return cursor.rowcount == 1

    def consume_counter(
        self,
        db_path: Path,
        *,
        user_id: int,
        counter: int,
    ) -> bool:
        normalized_user_id = _user_id(user_id)
        normalized_counter = _counter(counter)
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE user_mfa_credentials
                SET last_used_counter = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                  AND is_active = 1
                  AND (
                      last_used_counter IS NULL
                      OR last_used_counter < ?
                  )
                """,
                (normalized_counter, normalized_user_id, normalized_counter),
            )
        return cursor.rowcount == 1

    def delete(self, db_path: Path, user_id: int) -> bool:
        normalized_user_id = _user_id(user_id)
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                "DELETE FROM user_mfa_credentials WHERE user_id = ?",
                (normalized_user_id,),
            )
        return cursor.rowcount == 1


def _user_id(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("user_id must be a positive integer")
    return value


def _counter(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("counter must be a non-negative integer")
    return value


def _encrypted_secret(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("encrypted_secret must not be empty")
    return value.strip()
