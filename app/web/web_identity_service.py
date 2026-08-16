"""Web identity resolution for tenant-scoped user context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.repositories.user_repository import UserRepository
from app.services.tenant_context_service import TenantContextService


@dataclass(frozen=True)
class WebIdentity:
    """Resolved Web identity for one active user within one company."""

    user_id: int
    telegram_id: int
    company_id: str
    company_name: str
    role: str


class WebIdentityService:
    """Resolves Web-facing identity from telegram_id and company membership."""

    def __init__(
        self,
        user_repository: UserRepository,
        tenant_context_service: TenantContextService,
    ) -> None:
        self._user_repository = user_repository
        self._tenant_context_service = tenant_context_service

    def resolve(
        self,
        db_path: Path,
        telegram_id: int,
        company_id: str,
    ) -> Optional[WebIdentity]:
        """Return active Web identity for one telegram user and company, or None."""
        normalized_telegram_id = _validate_telegram_id(telegram_id)
        normalized_company_id = _validate_company_id(company_id)

        user_row = self._user_repository.get_by_telegram_id(
            db_path,
            normalized_telegram_id,
        )
        if user_row is None:
            return None
        if not bool(user_row["is_active"]):
            return None

        user_id = int(user_row["id"])
        persisted_telegram_id = int(user_row["telegram_id"])

        context = self._tenant_context_service.resolve(
            db_path,
            user_id,
            normalized_company_id,
        )
        if context is None:
            return None

        return WebIdentity(
            user_id=context.user_id,
            telegram_id=persisted_telegram_id,
            company_id=context.company_id,
            company_name=context.company_name,
            role=context.role,
        )


def _validate_telegram_id(telegram_id: int) -> int:
    if not isinstance(telegram_id, int) or isinstance(telegram_id, bool):
        raise ValueError("telegram_id must be an integer")
    if telegram_id <= 0:
        raise ValueError("telegram_id must be a positive integer")
    return telegram_id


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")
    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")
    return normalized
