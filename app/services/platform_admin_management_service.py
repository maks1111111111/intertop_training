"""Owner-governed lifecycle for additional global platform administrators."""

from __future__ import annotations

from pathlib import Path

from app.repositories.platform_admin_repository import (
    PlatformAdmin,
    PlatformAdminRepository,
)


class PlatformAdminManagementError(ValueError):
    """Raised when a platform-admin lifecycle action is not allowed."""


class PlatformAdminManagementService:
    """Grant and revoke non-owner platform access through the owner only."""

    def __init__(self, repository: PlatformAdminRepository) -> None:
        self._repository = repository

    def grant(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        target_user_id: int,
        reason: str,
    ) -> PlatformAdmin:
        self._require_owner(db_path, actor_user_id)
        normalized_reason = _validate_reason(reason)
        try:
            admin = self._repository.grant_admin(db_path, target_user_id)
        except ValueError as error:
            raise PlatformAdminManagementError(str(error)) from error
        self._repository.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="platform_admin.granted",
            target_type="user",
            target_id=str(admin.user_id),
            reason=normalized_reason,
        )
        return admin

    def revoke(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        target_user_id: int,
        reason: str,
    ) -> None:
        self._require_owner(db_path, actor_user_id)
        normalized_reason = _validate_reason(reason)
        try:
            revoked = self._repository.revoke_admin(db_path, target_user_id)
        except ValueError as error:
            raise PlatformAdminManagementError(str(error)) from error
        if not revoked:
            raise PlatformAdminManagementError("active platform admin not found")
        self._repository.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="platform_admin.revoked",
            target_type="user",
            target_id=str(target_user_id),
            reason=normalized_reason,
        )

    def _require_owner(self, db_path: Path, actor_user_id: int) -> None:
        actor = self._repository.get_active_by_user_id(db_path, actor_user_id)
        if actor is None or not actor.is_owner:
            raise PlatformAdminManagementError(
                "active platform owner access is required"
            )


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise PlatformAdminManagementError("reason is required")
    return reason.strip()
