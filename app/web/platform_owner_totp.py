"""Time-based one-time passwords for the sole platform owner."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass
from typing import Mapping, Optional


_ENVIRONMENT_KEY = "INTERTOP_PLATFORM_OWNER_TOTP_SECRET"


@dataclass(frozen=True)
class PlatformOwnerTOTP:
    """Verify RFC 6238 codes without persisting the shared secret in SQLite."""

    secret: Optional[bytes]
    period_seconds: int = 30
    digits: int = 6

    @classmethod
    def from_environment(
        cls,
        environment: Optional[Mapping[str, str]] = None,
    ) -> "PlatformOwnerTOTP":
        source = os.environ if environment is None else environment
        encoded = str(source.get(_ENVIRONMENT_KEY, "")).strip()
        if not encoded:
            return cls(secret=None)
        return cls(secret=_decode_secret(encoded))

    @property
    def is_configured(self) -> bool:
        return self.secret is not None

    def verify(self, code: str, *, at_time: Optional[int] = None) -> bool:
        """Accept a current code with one time-step of clock tolerance."""
        if self.secret is None:
            return False
        normalized = str(code).strip().replace(" ", "")
        if len(normalized) != self.digits or not normalized.isdigit():
            return False
        timestamp = int(time.time() if at_time is None else at_time)
        counter = timestamp // self.period_seconds
        for offset in (-1, 0, 1):
            candidate = _code_for_counter(
                self.secret,
                counter + offset,
                digits=self.digits,
            )
            if hmac.compare_digest(candidate, normalized):
                return True
        return False


def generate_base32_secret() -> str:
    """Return a 160-bit setup key suitable for an authenticator application."""
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _decode_secret(encoded: str) -> bytes:
    normalized = encoded.upper().replace(" ", "")
    padding = "=" * (-len(normalized) % 8)
    try:
        decoded = base64.b32decode(normalized + padding, casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            f"{_ENVIRONMENT_KEY} must be a valid Base32 secret"
        ) from exc
    if len(decoded) < 20:
        raise ValueError(f"{_ENVIRONMENT_KEY} must contain at least 160 bits")
    return decoded


def _code_for_counter(secret: bytes, counter: int, *, digits: int) -> str:
    digest = hmac.new(
        secret,
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)
