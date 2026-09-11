"""Resolve global platform access without consulting tenant memberships."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.repositories.platform_admin_repository import PlatformAdminRepository


@dataclass(frozen=True)
class PlatformAdminContext:
    user_id: int
    is_owner: bool


class PlatformAdminContextService:
    """Return only active, explicitly granted global platform identities."""

    def __init__(self, repository: PlatformAdminRepository) -> None:
        self._repository = repository

    def resolve_user(
        self,
        db_path: Path,
        user_id: int,
    ) -> Optional[PlatformAdminContext]:
        admin = self._repository.get_active_by_user_id(db_path, user_id)
        if admin is None:
            return None
        return PlatformAdminContext(
            user_id=admin.user_id,
            is_owner=admin.is_owner,
        )
