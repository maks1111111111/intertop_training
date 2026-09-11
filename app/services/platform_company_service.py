"""Owner-only company lifecycle operations for the platform contour."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.repositories.company_repository import Company, CompanyRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository


_COMPANY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class PlatformCompanyError(ValueError):
    """Raised for rejected platform company lifecycle operations."""


class PlatformCompanyService:
    """Mutate companies only for an active platform owner and audit every step."""

    def __init__(
        self,
        company_repository: CompanyRepository,
        platform_admin_repository: PlatformAdminRepository,
    ) -> None:
        self._companies = company_repository
        self._platform_admins = platform_admin_repository

    def create_company(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        company_id: str,
        name: str,
        reason: str,
    ) -> Company:
        """Provision a company and write its immutable audit event."""
        self._require_owner(db_path, actor_user_id)
        normalized_id = _validate_company_id(company_id)
        normalized_name = _validate_text(name, "name")
        normalized_reason = _validate_text(reason, "reason")
        try:
            company = self._companies.create(
                db_path,
                company_id=normalized_id,
                name=normalized_name,
            )
        except sqlite3.IntegrityError as error:
            raise PlatformCompanyError("company_id already exists") from error
        self._platform_admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="company.created",
            target_type="company",
            target_id=company.id,
            reason=normalized_reason,
        )
        return company

    def set_company_active(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        company_id: str,
        is_active: bool,
        reason: str,
    ) -> Company:
        """Activate or deactivate a company and record the operational reason."""
        self._require_owner(db_path, actor_user_id)
        normalized_id = _validate_company_id(company_id)
        normalized_reason = _validate_text(reason, "reason")
        if not isinstance(is_active, bool):
            raise PlatformCompanyError("is_active must be a boolean")

        company = self._companies.get_by_id(db_path, normalized_id)
        if company is None:
            raise PlatformCompanyError("company not found")
        if company.is_active == is_active:
            return company
        updated = self._companies.set_active(db_path, normalized_id, is_active)
        if not updated:
            raise RuntimeError("failed to update company state")
        refreshed = self._companies.get_by_id(db_path, normalized_id)
        if refreshed is None:
            raise RuntimeError("failed to load company after state change")
        self._platform_admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action=("company.activated" if is_active else "company.deactivated"),
            target_type="company",
            target_id=refreshed.id,
            reason=normalized_reason,
        )
        return refreshed

    def _require_owner(self, db_path: Path, actor_user_id: int) -> None:
        admin = self._platform_admins.get_active_by_user_id(db_path, actor_user_id)
        if admin is None or not admin.is_owner:
            raise PlatformCompanyError("active platform owner access is required")


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise PlatformCompanyError("company_id must be a string")
    normalized = company_id.strip().lower()
    if not _COMPANY_ID_PATTERN.fullmatch(normalized):
        raise PlatformCompanyError(
            "company_id must contain lowercase letters, digits, or hyphens"
        )
    return normalized


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise PlatformCompanyError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise PlatformCompanyError(f"{field_name} is required")
    return normalized
