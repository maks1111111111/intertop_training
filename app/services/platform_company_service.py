"""Owner-only company lifecycle operations for the platform contour."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from app.repositories.company_repository import Company, CompanyRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository


_COMPANY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_ARCHIVE_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ARCHIVE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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

    def rename_company(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        company_id: str,
        name: str,
        reason: str,
    ) -> Company:
        """Rename a company without changing its immutable tenant ID."""
        self._require_owner(db_path, actor_user_id)
        normalized_id = _validate_company_id(company_id)
        normalized_name = _validate_text(name, "name")
        normalized_reason = _validate_text(reason, "reason")

        company = self._companies.get_by_id(db_path, normalized_id)
        if company is None:
            raise PlatformCompanyError("company not found")
        if company.name == normalized_name:
            return company
        if not self._companies.set_name(db_path, normalized_id, normalized_name):
            raise RuntimeError("failed to update company name")
        renamed = self._companies.get_by_id(db_path, normalized_id)
        if renamed is None:
            raise RuntimeError("failed to load company after rename")
        self._platform_admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="company.renamed",
            target_type="company",
            target_id=renamed.id,
            reason=json.dumps(
                {
                    "new_name": renamed.name,
                    "old_name": company.name,
                    "operator_reason": normalized_reason,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        return renamed

    def record_company_data_export(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        company_id: str,
        archive_name: str,
        archive_sha256: str,
        reason: str,
    ) -> None:
        """Record an operator-verified customer export before offboarding.

        The archive remains outside the Web process.  This method records only
        its non-secret filename and SHA-256 fingerprint in the immutable
        platform audit trail, so a later destructive workflow has a durable
        prerequisite without exposing the customer archive in the UI.
        """
        self._require_owner(db_path, actor_user_id)
        normalized_id = _validate_company_id(company_id)
        normalized_name = _validate_archive_name(archive_name)
        normalized_sha256 = _validate_archive_sha256(archive_sha256)
        normalized_reason = _validate_text(reason, "reason")

        company = self._companies.get_by_id(db_path, normalized_id)
        if company is None:
            raise PlatformCompanyError("company not found")
        if not company.is_active:
            raise PlatformCompanyError(
                "company export must be recorded before the company is disabled"
            )

        self._platform_admins.append_audit_event(
            db_path,
            actor_user_id=actor_user_id,
            action="company.data_export_recorded",
            target_type="company",
            target_id=normalized_id,
            reason=(
                f"archive_name={normalized_name}; "
                f"archive_sha256={normalized_sha256}; "
                f"operator_reason={normalized_reason}"
            ),
        )

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


def _validate_archive_name(value: str) -> str:
    if not isinstance(value, str):
        raise PlatformCompanyError("archive_name must be a string")
    normalized = value.strip()
    if not _ARCHIVE_NAME_PATTERN.fullmatch(normalized):
        raise PlatformCompanyError(
            "archive_name must be a filename of at most 128 safe characters"
        )
    return normalized


def _validate_archive_sha256(value: str) -> str:
    if not isinstance(value, str):
        raise PlatformCompanyError("archive_sha256 must be a string")
    normalized = value.strip().lower()
    if not _ARCHIVE_SHA256_PATTERN.fullmatch(normalized):
        raise PlatformCompanyError("archive_sha256 must be a 64-character SHA-256 hex value")
    return normalized
