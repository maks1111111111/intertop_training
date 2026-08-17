"""Password-based authentication for canonical Web users."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from app.repositories.password_credential_repository import (
    PasswordCredentialRepository,
)
from app.web.password_hashing_service import PasswordHashingService
from app.web.web_identity_service import WebIdentity, WebIdentityService


PasswordValue = Union[str, bytes]

_DUMMY_PASSWORD = "intertop-authentication-dummy-password"


class WebAuthenticationService:
    """Authenticate password credentials into a tenant-scoped Web identity."""

    def __init__(
        self,
        credential_repository: PasswordCredentialRepository,
        password_hashing_service: PasswordHashingService,
        identity_service: WebIdentityService,
        *,
        dummy_password_hash: Optional[str] = None,
    ) -> None:
        self._credential_repository = credential_repository
        self._password_hashing_service = password_hashing_service
        self._identity_service = identity_service
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
        company_id: str,
    ) -> Optional[WebIdentity]:
        """Return an active tenant identity when credentials are valid."""
        normalized_company_id = _validate_company_id(company_id)
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

        if not verification.valid:
            return None

        if not credential.is_active:
            return None

        identity = self._identity_service.resolve_user(
            db_path,
            credential.user_id,
            normalized_company_id,
        )
        if identity is None:
            return None

        if verification.updated_hash is not None:
            updated = self._credential_repository.update_password_hash(
                db_path,
                credential.user_id,
                verification.updated_hash,
            )
            if not updated:
                return None

        return identity

    def _verify_dummy(self, password: PasswordValue) -> None:
        """Perform password verification for unknown accounts to reduce enumeration."""
        self._password_hashing_service.verify_password(
            password,
            self._dummy_password_hash,
        )


def _normalize_email(email: str) -> Optional[str]:
    if not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    return normalized


def _password_is_present(password: PasswordValue) -> bool:
    if not isinstance(password, (str, bytes)):
        return False
    return bool(password)


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")
    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")
    return normalized
