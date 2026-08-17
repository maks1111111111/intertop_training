"""Role-based authorization for resolved Web identities."""

from __future__ import annotations

from typing import Collection, Optional

from app.services.tenant_context_service import KNOWN_ROLES, MANAGEMENT_ROLES
from app.web.web_identity_service import WebIdentity


class WebAuthorizationService:
    """Evaluate role-based permissions for resolved Web identities."""

    def has_role(
        self,
        identity: Optional[WebIdentity],
        allowed_roles: Collection[str],
    ) -> bool:
        """Return True when identity has one of the allowed tenant roles."""
        normalized_allowed = _normalize_allowed_roles(allowed_roles)
        if identity is None or not normalized_allowed:
            return False
        return identity.role in normalized_allowed

    def can_manage_learning(self, identity: Optional[WebIdentity]) -> bool:
        """Return True for manager/admin identities allowed to manage learning."""
        return self.has_role(identity, MANAGEMENT_ROLES)

    def is_admin(self, identity: Optional[WebIdentity]) -> bool:
        """Return True only for an admin identity."""
        return self.has_role(identity, ("admin",))


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
