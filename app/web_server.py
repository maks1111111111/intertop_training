"""Validated Uvicorn entry point for the Intertop Training Web application."""

from __future__ import annotations

import os
from dataclasses import dataclass

import uvicorn

from app.env import load_project_env


WEB_HOST_ENV = "INTERTOP_WEB_HOST"
WEB_PORT_ENV = "INTERTOP_WEB_PORT"
FORWARDED_ALLOW_IPS_ENV = "INTERTOP_FORWARDED_ALLOW_IPS"


@dataclass(frozen=True)
class WebServerConfig:
    """Network settings for one Uvicorn process behind a reverse proxy."""

    host: str = "127.0.0.1"
    port: int = 8000
    forwarded_allow_ips: str = "127.0.0.1"

    @classmethod
    def from_environment(cls) -> "WebServerConfig":
        host = os.getenv(WEB_HOST_ENV, cls.host).strip()
        if not host:
            raise RuntimeError(f"{WEB_HOST_ENV} must not be empty.")

        raw_port = os.getenv(WEB_PORT_ENV, str(cls.port)).strip()
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise RuntimeError(f"{WEB_PORT_ENV} must be an integer.") from exc
        if not 1 <= port <= 65535:
            raise RuntimeError(f"{WEB_PORT_ENV} must be between 1 and 65535.")

        forwarded_allow_ips = os.getenv(
            FORWARDED_ALLOW_IPS_ENV,
            cls.forwarded_allow_ips,
        ).strip()
        if not forwarded_allow_ips:
            raise RuntimeError(f"{FORWARDED_ALLOW_IPS_ENV} must not be empty.")
        if forwarded_allow_ips == "*":
            raise RuntimeError(
                f"{FORWARDED_ALLOW_IPS_ENV} must list trusted proxy IP addresses, "
                "not '*'."
            )

        return cls(
            host=host,
            port=port,
            forwarded_allow_ips=forwarded_allow_ips,
        )


def main() -> None:
    """Run one Web process; the process manager owns restarts."""
    load_project_env()
    config = WebServerConfig.from_environment()
    uvicorn.run(
        "app.api.app:app",
        host=config.host,
        port=config.port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=config.forwarded_allow_ips,
        server_header=False,
    )


if __name__ == "__main__":
    main()
