"""Persistence layer for SaaS companies."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    is_active: bool
    created_at: str
    updated_at: str


def _row_to_company(row: sqlite3.Row) -> Company:
    return Company(
        id=str(row["id"]),
        name=str(row["name"]),
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _validate_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


class CompanyRepository:
    """Repository for tenant company records."""

    def create(
        self,
        db_path: Path,
        company_id: str,
        name: str,
    ) -> Company:
        normalized_id = _validate_non_empty(company_id, "company_id")
        normalized_name = _validate_non_empty(name, "name")

        with get_connection(db_path) as connection:
            connection.execute(
                """
                INSERT INTO companies (id, name)
                VALUES (?, ?)
                """,
                (normalized_id, normalized_name),
            )
            row = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE id = ?
                """,
                (normalized_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Failed to load company after insert")
        return _row_to_company(row)

    def get_by_id(
        self,
        db_path: Path,
        company_id: str,
    ) -> Optional[Company]:
        normalized_id = _validate_non_empty(company_id, "company_id")

        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE id = ?
                """,
                (normalized_id,),
            ).fetchone()

        if row is None:
            return None
        return _row_to_company(row)

    def list_active(
        self,
        db_path: Path,
    ) -> tuple[Company, ...]:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE is_active = 1
                ORDER BY id ASC
                """
            ).fetchall()

        return tuple(_row_to_company(row) for row in rows)

    def set_active(
        self,
        db_path: Path,
        company_id: str,
        is_active: bool,
    ) -> bool:
        normalized_id = _validate_non_empty(company_id, "company_id")
        active_value = 1 if is_active else 0

        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE companies
                SET is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (active_value, normalized_id),
            )

        return cursor.rowcount > 0
