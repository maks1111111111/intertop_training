"""Authenticate explicit platform administrators outside a tenant context."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.repositories.password_credential_repository import PasswordCredentialRepository
from app.services.platform_admin_context_service import PlatformAdminContext, PlatformAdminContextService
from app.web.password_hashing_service import PasswordHashingService
from app.web.web_authentication_service import PasswordValue, _password_is_present


_DUMMY_PASSWORD = "intertop-platform-authentication-dummy-password"


class PlatformAuthenticationService:
    """Verify credentials then resolve a global, non-tenant admin privilege."""

    def __init__(
        self,
        credential_repository: PasswordCredentialRepository,
        password_hashing_service: PasswordHashingService,
        context_service: PlatformAdminContextService,
        *,
        dummy_password_hash: Optional[str] = None,
    ) -> None:
        self._credential_repository = credential_repository
        self._password_hashing_service = password_hashing_service
        self._context_service = context_service
        self._dummy_password_hash = (
            dummy_password_hash
            if dummy_password_hash is not None
            else password_hashing_service.hash_password(_DUMMY_PASSWORD)
        )

    def authenticate(
        self,
        db_path: Path,
        *,
        email: str,
        password: PasswordValue,
    ) -> Optional[PlatformAdminContext]:
        normalized_email = _normalize_email(email)
        if normalized_email is None or not _password_is_present(password):
            return None

        credential = self._credential_repository.get_by_email(
            db_path,
            normalized_email,
        )
        if credential is None:
            self._verify_dummy(password)
            return None

        verification = self._password_hashing_service.verify_password(
            password,
            credential.password_hash,
        )
        if not verification.valid or not credential.is_active:
            return None

        context = self._context_service.resolve_user(
            db_path,
            credential.user_id,
        )
        if context is None:
            return None

        if verification.updated_hash is not None:
            updated = self._credential_repository.update_password_hash(
                db_path,
                credential.user_id,
                verification.updated_hash,
            )
            if not updated:
                return None

        return context

    def _verify_dummy(self, password: PasswordValue) -> None:
        self._password_hashing_service.verify_password(
            password,
            self._dummy_password_hash,
        )


def _normalize_email(email: str) -> Optional[str]:
    if not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    return normalized or None
