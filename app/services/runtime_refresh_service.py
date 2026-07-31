"""Public service for initiating Content Runtime refresh operations.

Provides a stable application-layer entry point for external interfaces
(Telegram, Web, REST API, Mobile) without exposing runtime internals.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.content.runtime_manager import (
    ContentRuntimeManager,
    RuntimeRefreshStats,
    RuntimeState,
)


@dataclass(frozen=True)
class RuntimeRefreshResult:
    """Result of a runtime refresh operation."""

    courses_before: int
    courses_after: int
    changed: bool
    refreshed_at: str


class RuntimeRefreshService:
    """Application service for runtime refresh and state inspection."""

    def __init__(self, manager: ContentRuntimeManager) -> None:
        self._manager = manager

    def refresh(self) -> RuntimeRefreshResult:
        """Refresh published content and return structured statistics."""
        stats = self._manager.refresh()
        return _stats_to_result(stats)

    def state(self) -> RuntimeState:
        """Return the current runtime state without triggering a refresh."""
        return self._manager.get_state()


def _stats_to_result(stats: RuntimeRefreshStats) -> RuntimeRefreshResult:
    """Map manager refresh statistics to the public service result."""
    return RuntimeRefreshResult(
        courses_before=stats.courses_before,
        courses_after=stats.courses_after,
        changed=stats.changed,
        refreshed_at=stats.refreshed_at,
    )
