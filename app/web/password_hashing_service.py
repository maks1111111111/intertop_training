"""Secure password hashing for Web authentication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from pwdlib import PasswordHash


PasswordValue = Union[str, bytes]


@dataclass(frozen=True)
class PasswordVerificationResult:
    """Result of verifying a plaintext password against a stored hash."""

    valid: bool
    updated_hash: Optional[str] = None


class PasswordHashingService:
    """Hash and verify Web passwords using the recommended Argon2 configuration."""

    def __init__(self, password_hash: Optional[PasswordHash] = None) -> None:
        self._password_hash = password_hash or PasswordHash.recommended()

    def hash_password(self, password: PasswordValue) -> str:
        """Return a password hash without persisting the plaintext password."""
        normalized = _validate_password(password)
        return self._password_hash.hash(normalized)

    def verify_password(
        self,
        password: PasswordValue,
        password_hash: str,
    ) -> PasswordVerificationResult:
        """Verify a password and return a replacement hash when rehash is needed."""
        normalized_password = _validate_password(password)
        normalized_hash = _validate_password_hash(password_hash)

        try:
            valid, updated_hash = self._password_hash.verify_and_update(
                normalized_password,
                normalized_hash,
            )
        except Exception:
            return PasswordVerificationResult(valid=False)

        if not valid:
            return PasswordVerificationResult(valid=False)

        return PasswordVerificationResult(
            valid=True,
            updated_hash=updated_hash,
        )


def _validate_password(password: PasswordValue) -> PasswordValue:
    if not isinstance(password, (str, bytes)):
        raise ValueError("password must be a string or bytes")
    if isinstance(password, str):
        if not password:
            raise ValueError("password must not be empty")
        return password
    if not password:
        raise ValueError("password must not be empty")
    return password


def _validate_password_hash(password_hash: str) -> str:
    if not isinstance(password_hash, str):
        raise ValueError("password_hash must be a string")
    normalized = password_hash.strip()
    if not normalized:
        raise ValueError("password_hash must not be empty")
    return normalized
