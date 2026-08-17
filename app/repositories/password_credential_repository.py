"""Persistence layer for password-based user credentials."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class PasswordCredential:
    id: int
    user_id: int
    email: str
    password_hash: str
    is_active: bool
    created_at: str
    updated_at: str


def _row_to_credential(row: sqlite3.Row) -> PasswordCredential:
    return PasswordCredential(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        email=str(row["email"]),
        password_hash=str(row["password_hash"]),
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("email must be a string")
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("email must not be empty")
    return normalized


def _validate_password_hash(password_hash: str) -> str:
    if not isinstance(password_hash, str):
        raise ValueError("password_hash must be a string")
    normalized = password_hash.strip()
    if not normalized:
        raise ValueError("password_hash must not be empty")
    return normalized


class PasswordCredentialRepository:
    """Repository for password-based authentication credentials."""

    def create(
        self,
        db_path: Path,
        *,
        user_id: int,
        email: str,
        password_hash: str,
    ) -> PasswordCredential:
        normalized_user_id = _validate_user_id(user_id)
        normalized_email = _normalize_email(email)
        normalized_hash = _validate_password_hash(password_hash)

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id,
                    email,
                    password_hash
                )
                VALUES (?, ?, ?)
                """,
                (
                    normalized_user_id,
                    normalized_email,
                    normalized_hash,
                ),
            )
            row = connection.execute(
                """
                SELECT *
                FROM user_password_credentials
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()

        if row is None:
            raise RuntimeError("Failed to load password credential after insert")
        return _row_to_credential(row)

    def get_by_email(
        self,
        db_path: Path,
        email: str,
    ) -> Optional[PasswordCredential]:
        normalized_email = _normalize_email(email)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM user_password_credentials
                WHERE email = ? COLLATE NOCASE
                """,
                (normalized_email,),
            ).fetchone()

        if row is None:
            return None
        return _row_to_credential(row)

    def get_by_user_id(
        self,
        db_path: Path,
        user_id: int,
    ) -> Optional[PasswordCredential]:
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM user_password_credentials
                WHERE user_id = ?
                """,
                (normalized_user_id,),
            ).fetchone()

        if row is None:
            return None
        return _row_to_credential(row)

    def update_password_hash(
        self,
        db_path: Path,
        user_id: int,
        password_hash: str,
    ) -> bool:
        normalized_user_id = _validate_user_id(user_id)
        normalized_hash = _validate_password_hash(password_hash)

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE user_password_credentials
                SET password_hash = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (normalized_hash, normalized_user_id),
            )

        return cursor.rowcount > 0

    def set_active(
        self,
        db_path: Path,
        user_id: int,
        is_active: bool,
    ) -> bool:
        normalized_user_id = _validate_user_id(user_id)
        active_value = 1 if is_active else 0

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE user_password_credentials
                SET is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (active_value, normalized_user_id),
            )

        return cursor.rowcount > 0
