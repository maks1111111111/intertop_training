"""Application service for resolving tenant-scoped user context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Optional

from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository

KNOWN_ROLES = frozenset({"student", "manager", "admin"})
MANAGEMENT_ROLES = frozenset({"manager", "admin"})


@dataclass(frozen=True)
class TenantUserContext:
    user_id: int
    company_id: str
    company_name: str
    role: str


class TenantContextService:
    """Resolves active company membership context for a user."""

    def __init__(
        self,
        company_repository: CompanyRepository,
        membership_repository: CompanyMembershipRepository,
    ) -> None:
        self._company_repository = company_repository
        self._membership_repository = membership_repository

    def resolve(
        self,
        db_path: Path,
        user_id: int,
        company_id: str,
    ) -> Optional[TenantUserContext]:
        """Return active tenant context for one user/company pair, or None."""
        normalized_user_id = _validate_user_id(user_id)
        normalized_company_id = _validate_company_id(company_id)

        company = self._company_repository.get_by_id(db_path, normalized_company_id)
        if company is None or not company.is_active:
            return None

        membership = self._membership_repository.get(
            db_path,
            normalized_company_id,
            normalized_user_id,
        )
        if membership is None or not membership.is_active:
            return None

        return TenantUserContext(
            user_id=normalized_user_id,
            company_id=company.id,
            company_name=company.name,
            role=membership.role,
        )

    def list_for_user(
        self,
        db_path: Path,
        user_id: int,
    ) -> tuple[TenantUserContext, ...]:
        """Return active tenant contexts for all active memberships of a user."""
        normalized_user_id = _validate_user_id(user_id)
        memberships = self._membership_repository.list_for_user(
            db_path,
            normalized_user_id,
            active_only=True,
        )

        contexts: list[TenantUserContext] = []
        for membership in memberships:
            company = self._company_repository.get_by_id(db_path, membership.company_id)
            if company is None or not company.is_active:
                continue
            contexts.append(
                TenantUserContext(
                    user_id=normalized_user_id,
                    company_id=company.id,
                    company_name=company.name,
                    role=membership.role,
                )
            )

        return tuple(contexts)

    def has_role(
        self,
        db_path: Path,
        user_id: int,
        company_id: str,
        allowed_roles: Collection[str],
    ) -> bool:
        """Return True when the user has an active context with one of the roles."""
        normalized_allowed = _normalize_allowed_roles(allowed_roles)
        if not normalized_allowed:
            return False

        context = self.resolve(db_path, user_id, company_id)
        if context is None:
            return False

        return context.role in normalized_allowed

    def can_manage_learning(
        self,
        db_path: Path,
        user_id: int,
        company_id: str,
    ) -> bool:
        """Return True when the user may manage learning content for the company."""
        return self.has_role(db_path, user_id, company_id, MANAGEMENT_ROLES)


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")
    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")
    return normalized


def _normalize_allowed_roles(allowed_roles: Collection[str]) -> frozenset[str]:
    normalized: set[str] = set()
    for role in allowed_roles:
        if not isinstance(role, str):
            raise ValueError("allowed role must be a string")
        candidate = role.strip().lower()
        if candidate not in KNOWN_ROLES:
            raise ValueError(f"Unsupported membership role: {role!r}")
        normalized.add(candidate)
    return frozenset(normalized)
