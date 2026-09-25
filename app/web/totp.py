"""Small RFC 6238 helpers shared by platform and tenant MFA."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import struct
import time
from typing import Optional


def generate_base32_secret() -> str:
    """Return a 160-bit setup key suitable for authenticator applications."""
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def decode_base32_secret(encoded: str, *, field_name: str) -> bytes:
    """Decode and validate a Base32 TOTP secret without logging its value."""
    normalized = str(encoded).strip().upper().replace(" ", "")
    padding = "=" * (-len(normalized) % 8)
    try:
        decoded = base64.b32decode(normalized + padding, casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid Base32 secret") from exc
    if len(decoded) < 20:
        raise ValueError(f"{field_name} must contain at least 160 bits")
    return decoded


def verify_totp(
    secret: bytes,
    code: str,
    *,
    at_time: Optional[int] = None,
    period_seconds: int = 30,
    digits: int = 6,
) -> Optional[int]:
    """Return the accepted counter, including one adjacent time step."""
    normalized = str(code).strip().replace(" ", "")
    if len(normalized) != digits or not normalized.isdigit():
        return None
    timestamp = int(time.time() if at_time is None else at_time)
    counter = timestamp // period_seconds
    for offset in (-1, 0, 1):
        accepted_counter = counter + offset
        if accepted_counter < 0:
            continue
        candidate = code_for_counter(secret, accepted_counter, digits=digits)
        if hmac.compare_digest(candidate, normalized):
            return accepted_counter
    return None


def code_for_counter(secret: bytes, counter: int, *, digits: int = 6) -> str:
    """Calculate one HOTP value for an already validated secret."""
    digest = hmac.new(
        secret,
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)
