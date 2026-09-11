"""Persistence for global platform administrators and immutable audit events."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


@dataclass(frozen=True)
class PlatformAdmin:
    """A global privilege deliberately separate from tenant roles."""

    user_id: int
    is_owner: bool
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PlatformAuditEvent:
    id: int
    actor_user_id: Optional[int]
    action: str
    target_type: str
    target_id: str
    reason: str
    created_at: str


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _row_to_platform_admin(row: sqlite3.Row) -> PlatformAdmin:
    return PlatformAdmin(
        user_id=int(row["user_id"]),
        is_owner=bool(row["is_owner"]),
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_audit_event(row: sqlite3.Row) -> PlatformAuditEvent:
    actor_user_id = row["actor_user_id"]
    return PlatformAuditEvent(
        id=int(row["id"]),
        actor_user_id=(int(actor_user_id) if actor_user_id is not None else None),
        action=str(row["action"]),
        target_type=str(row["target_type"]),
        target_id=str(row["target_id"]),
        reason=str(row["reason"]),
        created_at=str(row["created_at"]),
    )


class PlatformAdminRepository:
    """Store and resolve explicit global platform access."""

    def get_by_user_id(
        self,
        db_path: Path,
        user_id: int,
    ) -> Optional[PlatformAdmin]:
        normalized_user_id = _validate_user_id(user_id)
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT * FROM platform_admins WHERE user_id = ?",
                (normalized_user_id,),
            ).fetchone()
        return _row_to_platform_admin(row) if row is not None else None

    def get_active_by_user_id(
        self,
        db_path: Path,
        user_id: int,
    ) -> Optional[PlatformAdmin]:
        """Return access only for an active canonical user and admin record."""
        normalized_user_id = _validate_user_id(user_id)
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                SELECT platform_admins.*
                FROM platform_admins
                JOIN users ON users.id = platform_admins.user_id
                WHERE platform_admins.user_id = ?
                  AND platform_admins.is_active = 1
                  AND users.is_active = 1
                """,
                (normalized_user_id,),
            ).fetchone()
        return _row_to_platform_admin(row) if row is not None else None

    def bootstrap_owner(
        self,
        db_path: Path,
        user_id: int,
    ) -> PlatformAdmin:
        """Create the sole initial owner and refuse a second bootstrap."""
        normalized_user_id = _validate_user_id(user_id)
        with get_connection(db_path) as connection:
            user = connection.execute(
                "SELECT id FROM users WHERE id = ? AND is_active = 1",
                (normalized_user_id,),
            ).fetchone()
            if user is None:
                raise ValueError("user_id must reference an active user")

            owner = connection.execute(
                """
                SELECT user_id FROM platform_admins
                WHERE is_owner = 1 AND is_active = 1
                """
            ).fetchone()
            if owner is not None:
                existing_owner_id = int(owner["user_id"])
                if existing_owner_id == normalized_user_id:
                    current = connection.execute(
                        "SELECT * FROM platform_admins WHERE user_id = ?",
                        (normalized_user_id,),
                    ).fetchone()
                    assert current is not None
                    return _row_to_platform_admin(current)
                raise RuntimeError("an active platform owner already exists")

            existing = connection.execute(
                "SELECT * FROM platform_admins WHERE user_id = ?",
                (normalized_user_id,),
            ).fetchone()
            if existing is not None:
                raise RuntimeError("user already has an inactive platform role")

            connection.execute(
                """
                INSERT INTO platform_admins (user_id, is_owner, is_active)
                VALUES (?, 1, 1)
                """,
                (normalized_user_id,),
            )
            connection.execute(
                """
                INSERT INTO platform_audit_events (
                    actor_user_id, action, target_type, target_id, reason
                )
                VALUES (?, 'platform_admin.bootstrap_owner', 'user', ?, 'bootstrap_cli')
                """,
                (normalized_user_id, str(normalized_user_id)),
            )
            row = connection.execute(
                "SELECT * FROM platform_admins WHERE user_id = ?",
                (normalized_user_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("failed to load platform owner after bootstrap")
        return _row_to_platform_admin(row)

    def list_audit_events(
        self,
        db_path: Path,
        *,
        limit: int = 100,
    ) -> tuple[PlatformAuditEvent, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer")
        if limit < 1 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")
        with get_connection(db_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM platform_audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(_row_to_audit_event(row) for row in rows)
