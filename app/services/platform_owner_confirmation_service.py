"""Require a fresh password check before a high-impact platform action."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from app.repositories.password_credential_repository import (
    PasswordCredentialRepository,
)
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.web.password_hashing_service import PasswordHashingService


PasswordValue = Union[str, bytes]


class PlatformOwnerConfirmationService:
    """Verify the current owner password without retaining its plaintext."""

    def __init__(
        self,
        credential_repository: PasswordCredentialRepository,
        platform_admin_repository: PlatformAdminRepository,
        password_hashing_service: PasswordHashingService,
    ) -> None:
        self._credentials = credential_repository
        self._admins = platform_admin_repository
        self._passwords = password_hashing_service

    def confirm(
        self,
        db_path: Path,
        *,
        owner_user_id: int,
        password: PasswordValue,
    ) -> bool:
        """Return whether an active owner freshly proved their password."""
        admin = self._admins.get_active_by_user_id(db_path, owner_user_id)
        if admin is None or not admin.is_owner:
            return False
        credential = self._credentials.get_by_user_id(db_path, owner_user_id)
        if credential is None or not credential.is_active:
            return False
        try:
            result = self._passwords.verify_password(password, credential.password_hash)
        except ValueError:
            return False
        if not result.valid:
            return False
        if result.updated_hash is not None:
            return self._credentials.update_password_hash(
                db_path,
                owner_user_id,
                result.updated_hash,
            )
        return True
