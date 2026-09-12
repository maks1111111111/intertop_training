"""Least-privilege, audited and time-bound company support access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.repositories.company_repository import CompanyRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.repositories.platform_support_access_repository import (
    PlatformSupportAccess,
    PlatformSupportAccessRepository,
)


MIN_SUPPORT_DURATION_MINUTES = 5
MAX_SUPPORT_DURATION_MINUTES = 60


class PlatformSupportAccessError(ValueError):
    """Raised when a support access request is invalid or unauthorized."""


class PlatformSupportAccessService:
    """Issue only explicit read-only support grants for one company at a time."""

    def __init__(
        self,
        support_repository: PlatformSupportAccessRepository,
        platform_admin_repository: PlatformAdminRepository,
        company_repository: CompanyRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._support = support_repository
        self._admins = platform_admin_repository
        self._companies = company_repository
        self._clock = clock

    def grant(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        operator_user_id: int,
        company_id: str,
        reason: str,
        duration_minutes: int,
    ) -> PlatformSupportAccess:
        self._require_owner(db_path, actor_user_id)
        operator = self._admins.get_active_by_user_id(db_path, operator_user_id)
        if operator is None:
            raise PlatformSupportAccessError("operator must be an active platform admin")
        company = self._companies.get_by_id(db_path, company_id)
        if company is None:
            raise PlatformSupportAccessError("company not found")
        if not company.is_active:
            raise PlatformSupportAccessError("company must be active")
        normalized_reason = _validate_reason(reason)
        duration = _validate_duration(duration_minutes)
        now = self._now()
        access = self._support.create(
            db_path,
            operator_user_id=operator.user_id,
            company_id=company.id,
            reason=normalized_reason,
            expires_at=now + timedelta(minutes=duration),
        )
        self._admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="support_access.granted",
            target_type="support_access",
            target_id=str(access.id),
            reason=normalized_reason,
        )
        return access

    def resolve_for_operator(
        self,
        db_path: Path,
        *,
        access_id: int,
        operator_user_id: int,
    ) -> PlatformSupportAccess | None:
        if self._admins.get_active_by_user_id(db_path, operator_user_id) is None:
            return None
        access = self._support.get_active_for_operator(
            db_path,
            access_id=access_id,
            operator_user_id=operator_user_id,
            now=self._now(),
        )
        if access is None:
            return None
        company = self._companies.get_by_id(db_path, access.company_id)
        if company is None or not company.is_active:
            return None
        self._admins.append_audit_event(
            db_path,
            actor_user_id=operator_user_id,
            action="support_access.read_only_diagnostics_viewed",
            target_type="support_access",
            target_id=str(access.id),
            reason=access.reason,
        )
        return access

    def list_active(self, db_path: Path) -> tuple[PlatformSupportAccess, ...]:
        """List currently usable grants for the platform owner dashboard."""
        return self._support.list_active(db_path, now=self._now())

    def list_active_for_operator(
        self,
        db_path: Path,
        *,
        operator_user_id: int,
    ) -> tuple[PlatformSupportAccess, ...]:
        """List only the grants assigned to one active platform operator."""
        if self._admins.get_active_by_user_id(db_path, operator_user_id) is None:
            return ()
        accesses = self._support.list_active_for_operator(
            db_path,
            operator_user_id=operator_user_id,
            now=self._now(),
        )
        return tuple(
            access
            for access in accesses
            if (company := self._companies.get_by_id(db_path, access.company_id))
            is not None
            and company.is_active
        )

    def revoke(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        access_id: int,
        reason: str,
    ) -> None:
        self._require_owner(db_path, actor_user_id)
        normalized_reason = _validate_reason(reason)
        if not self._support.revoke(db_path, access_id, now=self._now()):
            raise PlatformSupportAccessError("active support access not found")
        self._admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="support_access.revoked",
            target_type="support_access",
            target_id=str(access_id),
            reason=normalized_reason,
        )

    def _require_owner(self, db_path: Path, user_id: int) -> None:
        actor = self._admins.get_active_by_user_id(db_path, user_id)
        if actor is None or not actor.is_owner:
            raise PlatformSupportAccessError("active platform owner access is required")

    def _now(self) -> datetime:
        return self._clock().astimezone(timezone.utc)


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise PlatformSupportAccessError("reason is required")
    return reason.strip()


def _validate_duration(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PlatformSupportAccessError("duration_minutes must be an integer")
    if not MIN_SUPPORT_DURATION_MINUTES <= value <= MAX_SUPPORT_DURATION_MINUTES:
        raise PlatformSupportAccessError(
            "duration_minutes must be between 5 and 60"
        )
    return value
