"""Authenticated encryption for tenant administrator MFA secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from cryptography.fernet import Fernet, InvalidToken


MFA_ENCRYPTION_KEY_ENV = "INTERTOP_MFA_ENCRYPTION_KEY"


@dataclass(frozen=True)
class MFASecretCipher:
    """Encrypt TOTP setup keys with a server-only Fernet key."""

    _fernet: Optional[Fernet]

    @classmethod
    def from_environment(
        cls,
        environment: Optional[Mapping[str, str]] = None,
    ) -> "MFASecretCipher":
        source = os.environ if environment is None else environment
        raw_key = str(source.get(MFA_ENCRYPTION_KEY_ENV, "")).strip()
        if not raw_key:
            return cls(_fernet=None)
        try:
            fernet = Fernet(raw_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError(
                f"{MFA_ENCRYPTION_KEY_ENV} must be a valid Fernet key"
            ) from exc
        return cls(_fernet=fernet)

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, secret: str) -> str:
        if self._fernet is None:
            raise RuntimeError("tenant MFA encryption is not configured")
        return self._fernet.encrypt(secret.encode("ascii")).decode("ascii")

    def decrypt(self, encrypted_secret: str) -> str:
        if self._fernet is None:
            raise RuntimeError("tenant MFA encryption is not configured")
        try:
            return self._fernet.decrypt(
                encrypted_secret.encode("ascii")
            ).decode("ascii")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise ValueError("stored MFA secret cannot be decrypted") from exc
