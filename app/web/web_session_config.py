"""Configuration for signed Web sessions."""

from __future__ import annotations

import os
from dataclasses import dataclass


WEB_SESSION_SECRET_ENV = "WEB_SESSION_SECRET"
WEB_SESSION_COOKIE_NAME = "intertop_session"
MIN_WEB_SESSION_SECRET_BYTES = 32


@dataclass(frozen=True)
class WebSessionConfig:
    """Signed Web session settings loaded from environment variables."""

    secret_key: str

    @classmethod
    def from_environment(cls) -> "WebSessionConfig":
        """Load and validate ``WEB_SESSION_SECRET`` from the environment."""
        secret_key = os.getenv(WEB_SESSION_SECRET_ENV)

        if secret_key is None:
            raise RuntimeError(
                "WEB_SESSION_SECRET environment variable is not set."
            )

        if not secret_key.strip():
            raise RuntimeError(
                "WEB_SESSION_SECRET environment variable must not be empty."
            )

        if len(secret_key.encode("utf-8")) < MIN_WEB_SESSION_SECRET_BYTES:
            raise RuntimeError(
                "WEB_SESSION_SECRET environment variable must contain "
                "at least 32 bytes."
            )

        return cls(secret_key=secret_key)
