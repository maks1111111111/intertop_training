"""Enrollment and verification of MFA for tenant administrators."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

from app.repositories.user_mfa_repository import UserMFARepository
from app.web.mfa_secret_cipher import MFASecretCipher
from app.web.totp import (
    decode_base32_secret,
    generate_base32_secret,
    verify_totp,
)


@dataclass(frozen=True)
class MFAEnrollment:
    secret: str
    authenticator_uri: str


class CompanyAdminMFAService:
    """Manage encrypted TOTP credentials and prevent code replay."""

    def __init__(
        self,
        repository: UserMFARepository,
        cipher: MFASecretCipher,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._clock = clock

    @property
    def is_configured(self) -> bool:
        return self._cipher.is_configured

    def is_enrolled(self, db_path: Path, user_id: int) -> bool:
        credential = self._repository.get(db_path, user_id)
        return credential is not None and credential.is_active

    def begin_enrollment(
        self,
        db_path: Path,
        *,
        user_id: int,
        email: str,
    ) -> MFAEnrollment:
        secret = generate_base32_secret()
        self._repository.replace_pending(
            db_path,
            user_id=user_id,
            encrypted_secret=self._cipher.encrypt(secret),
        )
        return self._enrollment(secret, email)

    def get_pending_enrollment(
        self,
        db_path: Path,
        *,
        user_id: int,
        email: str,
    ) -> Optional[MFAEnrollment]:
        credential = self._repository.get(db_path, user_id)
        if credential is None or credential.is_active:
            return None
        try:
            secret = self._cipher.decrypt(credential.encrypted_secret)
        except (RuntimeError, ValueError):
            return None
        return self._enrollment(secret, email)

    def activate(
        self,
        db_path: Path,
        *,
        user_id: int,
        code: str,
    ) -> bool:
        credential = self._repository.get(db_path, user_id)
        if credential is None or credential.is_active:
            return False
        try:
            counter = self._accepted_counter(credential.encrypted_secret, code)
        except (RuntimeError, ValueError):
            return False
        if counter is None:
            return False
        return self._repository.activate(
            db_path,
            user_id=user_id,
            counter=counter,
        )

    def verify_login(
        self,
        db_path: Path,
        *,
        user_id: int,
        code: str,
    ) -> bool:
        credential = self._repository.get(db_path, user_id)
        if credential is None or not credential.is_active:
            return False
        try:
            counter = self._accepted_counter(credential.encrypted_secret, code)
        except (RuntimeError, ValueError):
            return False
        if counter is None:
            return False
        return self._repository.consume_counter(
            db_path,
            user_id=user_id,
            counter=counter,
        )

    def reset(self, db_path: Path, user_id: int) -> bool:
        return self._repository.delete(db_path, user_id)

    def _accepted_counter(self, encrypted_secret: str, code: str) -> Optional[int]:
        encoded_secret = self._cipher.decrypt(encrypted_secret)
        secret = decode_base32_secret(encoded_secret, field_name="MFA secret")
        at_time = int(self._clock()) if self._clock is not None else None
        return verify_totp(secret, code, at_time=at_time)

    @staticmethod
    def _enrollment(secret: str, email: str) -> MFAEnrollment:
        issuer = quote("Mentor Connect", safe="")
        label = quote(f"Mentor Connect:{email.strip().lower()}", safe="")
        return MFAEnrollment(
            secret=secret,
            authenticator_uri=(
                f"otpauth://totp/{label}?secret={secret}"
                f"&issuer={issuer}&digits=6&period=30"
            ),
        )
