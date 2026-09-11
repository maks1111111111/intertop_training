"""Persistence for explicit, time-bound platform support access."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class PlatformSupportAccess:
    id: int
    operator_user_id: int
    company_id: str
    reason: str
    expires_at: datetime
    revoked_at: Optional[datetime]
    created_at: datetime


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _row_to_access(row: sqlite3.Row) -> PlatformSupportAccess:
    revoked_at = row["revoked_at"]
    return PlatformSupportAccess(
        id=int(row["id"]),
        operator_user_id=int(row["operator_user_id"]),
        company_id=str(row["company_id"]),
        reason=str(row["reason"]),
        expires_at=_parse_timestamp(str(row["expires_at"])),
        revoked_at=(_parse_timestamp(str(revoked_at)) if revoked_at else None),
        created_at=_parse_timestamp(str(row["created_at"])),
    )


class PlatformSupportAccessRepository:
    """Store grants that are limited to one operator and one company."""

    def create(
        self,
        db_path: Path,
        *,
        operator_user_id: int,
        company_id: str,
        reason: str,
        expires_at: datetime,
    ) -> PlatformSupportAccess:
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO platform_support_accesses (
                    operator_user_id, company_id, reason, expires_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    operator_user_id,
                    company_id,
                    reason,
                    _serialize_timestamp(expires_at),
                ),
            )
            row = connection.execute(
                "SELECT * FROM platform_support_accesses WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to load support access after create")
        return _row_to_access(row)

    def get_active_for_operator(
        self,
        db_path: Path,
        *,
        access_id: int,
        operator_user_id: int,
        now: datetime,
    ) -> Optional[PlatformSupportAccess]:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM platform_support_accesses
                WHERE id = ?
                  AND operator_user_id = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (access_id, operator_user_id, _serialize_timestamp(now)),
            ).fetchone()
        return _row_to_access(row) if row is not None else None

    def revoke(self, db_path: Path, access_id: int, *, now: datetime) -> bool:
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE platform_support_accesses
                SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (_serialize_timestamp(now), access_id),
            )
        return cursor.rowcount > 0
