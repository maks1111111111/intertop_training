"""Persistence layer for company membership records."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection

_ALLOWED_ROLES = frozenset({"student", "manager", "admin"})


@dataclass(frozen=True)
class CompanyMembership:
    id: int
    company_id: str
    user_id: int
    role: str
    is_active: bool
    created_at: str
    updated_at: str


def _row_to_membership(row: sqlite3.Row) -> CompanyMembership:
    return CompanyMembership(
        id=int(row["id"]),
        company_id=str(row["company_id"]),
        user_id=int(row["user_id"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _validate_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in _ALLOWED_ROLES:
        raise ValueError(f"Unsupported membership role: {role!r}")
    return normalized


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


class CompanyMembershipRepository:
    """Repository for user membership within a company."""

    def add(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
        role: str = "student",
    ) -> CompanyMembership:
        normalized_company_id = _validate_non_empty(company_id, "company_id")
        normalized_user_id = _validate_user_id(user_id)
        normalized_role = _validate_role(role)

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO company_memberships (
                    company_id,
                    user_id,
                    role
                )
                VALUES (?, ?, ?)
                """,
                (normalized_company_id, normalized_user_id, normalized_role),
            )
            row = connection.execute(
                """
                SELECT *
                FROM company_memberships
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()

        if row is None:
            raise RuntimeError("Failed to load membership after insert")
        return _row_to_membership(row)

    def get(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
    ) -> Optional[CompanyMembership]:
        normalized_company_id = _validate_non_empty(company_id, "company_id")
        normalized_user_id = _validate_user_id(user_id)

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM company_memberships
                WHERE company_id = ?
                  AND user_id = ?
                """,
                (normalized_company_id, normalized_user_id),
            ).fetchone()

        if row is None:
            return None
        return _row_to_membership(row)

    def list_for_company(
        self,
        db_path: Path,
        company_id: str,
        active_only: bool = True,
    ) -> tuple[CompanyMembership, ...]:
        normalized_company_id = _validate_non_empty(company_id, "company_id")

        query = """
            SELECT *
            FROM company_memberships
            WHERE company_id = ?
        """
        params: list[object] = [normalized_company_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY id ASC"

        with get_connection(db_path) as connection:
            rows = connection.execute(query, params).fetchall()

        return tuple(_row_to_membership(row) for row in rows)

    def list_for_user(
        self,
        db_path: Path,
        user_id: int,
        active_only: bool = True,
    ) -> tuple[CompanyMembership, ...]:
        normalized_user_id = _validate_user_id(user_id)

        query = """
            SELECT *
            FROM company_memberships
            WHERE user_id = ?
        """
        params: list[object] = [normalized_user_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY id ASC"

        with get_connection(db_path) as connection:
            rows = connection.execute(query, params).fetchall()

        return tuple(_row_to_membership(row) for row in rows)

    def set_role(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
        role: str,
    ) -> bool:
        normalized_company_id = _validate_non_empty(company_id, "company_id")
        normalized_user_id = _validate_user_id(user_id)
        normalized_role = _validate_role(role)

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE company_memberships
                SET role = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = ?
                  AND user_id = ?
                """,
                (normalized_role, normalized_company_id, normalized_user_id),
            )

        return cursor.rowcount > 0

    def set_active(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
        is_active: bool,
    ) -> bool:
        normalized_company_id = _validate_non_empty(company_id, "company_id")
        normalized_user_id = _validate_user_id(user_id)
        active_value = 1 if is_active else 0

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE company_memberships
                SET is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE company_id = ?
                  AND user_id = ?
                """,
                (active_value, normalized_company_id, normalized_user_id),
            )

        return cursor.rowcount > 0
