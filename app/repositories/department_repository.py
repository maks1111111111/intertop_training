"""Persistence operations for company departments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class Department:
    id: int
    company_id: str
    name: str
    is_active: bool


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


def _to_department(row) -> Department:
    return Department(
        id=int(row["id"]), company_id=str(row["company_id"]),
        name=str(row["name"]), is_active=bool(row["is_active"]),
    )


class DepartmentRepository:
    """Read and create departments within exactly one company."""

    def create(self, db_path: Path, company_id: str, name: str) -> Department:
        company_id = _required(company_id, "company_id")
        name = _required(name, "name")
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO departments (company_id, name) VALUES (?, ?)",
                (company_id, name),
            )
            row = connection.execute(
                "SELECT * FROM departments WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to load department after insert")
        return _to_department(row)

    def get(self, db_path: Path, company_id: str, department_id: int) -> Optional[Department]:
        company_id = _required(company_id, "company_id")
        if not isinstance(department_id, int) or isinstance(department_id, bool) or department_id <= 0:
            raise ValueError("department_id must be a positive integer")
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT * FROM departments WHERE company_id = ? AND id = ?",
                (company_id, department_id),
            ).fetchone()
        return _to_department(row) if row is not None else None

    def list_for_company(self, db_path: Path, company_id: str, *, active_only: bool = True) -> tuple[Department, ...]:
        company_id = _required(company_id, "company_id")
        query = "SELECT * FROM departments WHERE company_id = ?"
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY name COLLATE NOCASE, id"
        with get_connection(db_path) as connection:
            rows = connection.execute(query, (company_id,)).fetchall()
        return tuple(_to_department(row) for row in rows)
