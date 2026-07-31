"""Application service for administrative runtime refresh operations.

Provides a dedicated entry point for admin interfaces (Telegram Admin, Web Admin,
REST API, Mobile Admin) without coupling them directly to runtime refresh internals.
"""

from __future__ import annotations

from app.services.runtime_refresh_service import (
    RuntimeRefreshResult,
    RuntimeRefreshService,
)


class AdminRuntimeService:
    """Application-layer service for administrative runtime refresh."""

    def __init__(self, refresh_service: RuntimeRefreshService) -> None:
        self._refresh_service = refresh_service

    def refresh_runtime(self) -> RuntimeRefreshResult:
        """Refresh published content and return structured statistics."""
        return self._refresh_service.refresh()
