"""Validated deployment profile for local, staging, and production runs."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.web.web_session_config import WebSessionConfig


DEPLOYMENT_ENV = "INTERTOP_ENV"
ALLOWED_HOSTS_ENV = "INTERTOP_ALLOWED_HOSTS"

_DEVELOPMENT = "development"
_REMOTE_ENVIRONMENTS = frozenset({"staging", "production"})
_VALID_ENVIRONMENTS = frozenset({_DEVELOPMENT, *_REMOTE_ENVIRONMENTS})
_EXAMPLE_SESSION_SECRET = "replace-with-a-random-secret-at-least-32-bytes"


@dataclass(frozen=True)
class DeploymentConfig:
    """Security-sensitive settings selected for one deployment environment."""

    environment: str
    allowed_hosts: tuple[str, ...]
    force_secure_session_cookie: bool

    @classmethod
    def from_environment(cls) -> "DeploymentConfig":
        """Load and validate the active deployment profile."""
        environment = os.getenv(DEPLOYMENT_ENV, _DEVELOPMENT).strip().lower()
        if environment not in _VALID_ENVIRONMENTS:
            allowed = ", ".join(sorted(_VALID_ENVIRONMENTS))
            raise RuntimeError(f"{DEPLOYMENT_ENV} must be one of: {allowed}.")

        configured_hosts = os.getenv(ALLOWED_HOSTS_ENV)
        if environment in _REMOTE_ENVIRONMENTS:
            allowed_hosts = _parse_required_hosts(configured_hosts)
            session_config = WebSessionConfig.from_environment()
            if session_config.secret_key.strip() == _EXAMPLE_SESSION_SECRET:
                raise RuntimeError(
                    "WEB_SESSION_SECRET must not use the example value in "
                    f"{environment}."
                )
        elif configured_hosts is None:
            allowed_hosts = ("*",)
        else:
            allowed_hosts = _parse_hosts(configured_hosts)

        return cls(
            environment=environment,
            allowed_hosts=allowed_hosts,
            force_secure_session_cookie=environment in _REMOTE_ENVIRONMENTS,
        )


def _parse_required_hosts(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None:
        raise RuntimeError(
            f"{ALLOWED_HOSTS_ENV} is required for staging and production."
        )
    hosts = _parse_hosts(raw_value)
    if "*" in hosts:
        raise RuntimeError(
            f"{ALLOWED_HOSTS_ENV} must not contain '*' in staging or production."
        )
    return hosts


def _parse_hosts(raw_value: str) -> tuple[str, ...]:
    hosts = tuple(
        dict.fromkeys(part.strip().lower() for part in raw_value.split(","))
    )
    if not hosts or any(not host for host in hosts):
        raise RuntimeError(f"{ALLOWED_HOSTS_ENV} must contain host names.")

    for host in hosts:
        if (
            ":" in host
            or "/" in host
            or any(character.isspace() for character in host)
        ):
            raise RuntimeError(
                f"{ALLOWED_HOSTS_ENV} contains an invalid host: {host!r}."
            )
    return hosts
