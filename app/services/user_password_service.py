"""Password changes and temporary-password resets for tenant users."""

from __future__ import annotations

from pathlib import Path

from app.repositories.password_credential_repository import (
    PasswordCredentialRepository,
)
from app.web.password_hashing_service import PasswordHashingService


_MINIMUM_PASSWORD_LENGTH = 12


class UserPasswordError(ValueError):
    """Raised when a password operation cannot be completed safely."""


class UserPasswordService:
    """Change own passwords and issue temporary passwords without exposing hashes."""

    def __init__(
        self,
        credential_repository: PasswordCredentialRepository,
        password_hashing_service: PasswordHashingService,
    ) -> None:
        self._credentials = credential_repository
        self._passwords = password_hashing_service

    def change_password(
        self,
        db_path: Path,
        *,
        user_id: int,
        current_password: str,
        new_password: str,
        confirmation: str,
    ) -> None:
        credential = self._credentials.get_by_user_id(db_path, user_id)
        if credential is None or not credential.is_active:
            raise UserPasswordError("Учётная запись недоступна.")
        if not isinstance(current_password, str) or not current_password:
            raise UserPasswordError("Укажите текущий пароль.")
        verification = self._passwords.verify_password(
            current_password,
            credential.password_hash,
        )
        if not verification.valid:
            raise UserPasswordError("Текущий пароль указан неверно.")
        normalized = _validate_new_password(new_password, confirmation)
        same_password = self._passwords.verify_password(
            normalized,
            credential.password_hash,
        )
        if same_password.valid:
            raise UserPasswordError("Новый пароль должен отличаться от текущего.")
        password_hash = self._passwords.hash_password(normalized)
        if not self._credentials.replace_password(
            db_path,
            user_id,
            password_hash,
            must_change_password=False,
        ):
            raise UserPasswordError("Не удалось изменить пароль.")

    def reset_to_temporary_password(
        self,
        db_path: Path,
        *,
        actor_user_id: int,
        actor_password: str,
        user_id: int,
        temporary_password: str,
        confirmation: str,
    ) -> None:
        actor_credential = self._credentials.get_by_user_id(db_path, actor_user_id)
        if actor_credential is None or not actor_credential.is_active:
            raise UserPasswordError("Не удалось подтвердить текущий пароль.")
        if not isinstance(actor_password, str) or not actor_password:
            raise UserPasswordError("Не удалось подтвердить текущий пароль.")
        actor_verification = self._passwords.verify_password(
            actor_password,
            actor_credential.password_hash,
        )
        if not actor_verification.valid:
            raise UserPasswordError("Не удалось подтвердить текущий пароль.")
        credential = self._credentials.get_by_user_id(db_path, user_id)
        if credential is None or not credential.is_active:
            raise UserPasswordError("Учётная запись недоступна.")
        normalized = _validate_new_password(temporary_password, confirmation)
        password_hash = self._passwords.hash_password(normalized)
        if not self._credentials.replace_password(
            db_path,
            user_id,
            password_hash,
            must_change_password=True,
        ):
            raise UserPasswordError("Не удалось сбросить пароль.")


def _validate_new_password(password: str, confirmation: str) -> str:
    if not isinstance(password, str) or len(password) < _MINIMUM_PASSWORD_LENGTH:
        raise UserPasswordError("Пароль должен содержать не менее 12 символов.")
    if password != confirmation:
        raise UserPasswordError("Пароли не совпадают.")
    return password
