"""Signed Web session tokens for canonical authenticated users."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Callable, Optional


DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 12


@dataclass(frozen=True)
class WebSession:
    """Authenticated canonical Web session."""

    user_id: int
    company_id: str
    issued_at: int
    expires_at: int


class WebSessionService:
    """Create and verify signed Web session tokens."""

    def __init__(
        self,
        secret_key: str,
        *,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret_key = _validate_secret_key(secret_key)
        self._ttl_seconds = _validate_ttl_seconds(ttl_seconds)
        self._clock = clock

    def create_token(
        self,
        *,
        user_id: int,
        company_id: str,
    ) -> str:
        """Return a signed session token for one canonical user."""
        normalized_user_id = _validate_user_id(user_id)
        normalized_company_id = _validate_company_id(company_id)

        issued_at = int(self._clock())
        payload = {
            "user_id": normalized_user_id,
            "company_id": normalized_company_id,
            "issued_at": issued_at,
            "expires_at": issued_at + self._ttl_seconds,
        }

        encoded_payload = _encode_payload(payload)
        signature = self._sign(encoded_payload)

        return f"{encoded_payload}.{signature}"

    def resolve_token(self, token: str) -> Optional[WebSession]:
        """Return a verified session, or None for invalid/expired tokens."""
        if not isinstance(token, str) or not token:
            return None

        parts = token.split(".")
        if len(parts) != 2:
            return None

        encoded_payload, supplied_signature = parts
        if not encoded_payload or not supplied_signature:
            return None

        expected_signature = self._sign(encoded_payload)
        if not hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ):
            return None

        payload = _decode_payload(encoded_payload)
        if payload is None:
            return None

        try:
            user_id = _validate_user_id(payload["user_id"])
            company_id = _validate_company_id(payload["company_id"])
            issued_at = _validate_timestamp(payload["issued_at"])
            expires_at = _validate_timestamp(payload["expires_at"])
        except (KeyError, TypeError, ValueError):
            return None

        if expires_at <= issued_at:
            return None

        now = int(self._clock())
        if expires_at <= now:
            return None

        if issued_at > now:
            return None

        return WebSession(
            user_id=user_id,
            company_id=company_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def _sign(self, encoded_payload: str) -> str:
        digest = hmac.new(
            self._secret_key,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return _urlsafe_b64encode(digest)


def _encode_payload(payload: dict) -> str:
    raw = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _urlsafe_b64encode(raw)


def _decode_payload(encoded_payload: str) -> Optional[dict]:
    try:
        raw = _urlsafe_b64decode(encoded_payload)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _validate_secret_key(secret_key: str) -> bytes:
    if not isinstance(secret_key, str):
        raise ValueError("secret_key must be a string")

    encoded = secret_key.encode("utf-8")
    if len(encoded) < 32:
        raise ValueError("secret_key must contain at least 32 bytes")

    return encoded


def _validate_ttl_seconds(ttl_seconds: int) -> int:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
        raise ValueError("ttl_seconds must be an integer")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    return ttl_seconds


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")

    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")

    return normalized


def _validate_timestamp(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("timestamp must be an integer")
    if value < 0:
        raise ValueError("timestamp must not be negative")
    return value
