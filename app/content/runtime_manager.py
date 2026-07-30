"""Runtime lifecycle management for the Content Engine.

Provides a thin service layer over :class:`ContentRuntime` for explicit
content refresh operations with structured statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.content.runtime import ContentRuntime


@dataclass(frozen=True)
class RuntimeState:
    """Current snapshot of the managed runtime state."""

    courses_count: int
    last_refreshed_at: Optional[str]


@dataclass(frozen=True)
class RuntimeRefreshStats:
    """Statistics returned after a runtime refresh operation."""

    courses_before: int
    courses_after: int
    refreshed_at: str
    changed: bool


def _utc_timestamp() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ContentRuntimeManager:
    """Coordinates explicit refresh of a :class:`ContentRuntime` instance."""

    def __init__(self, runtime: ContentRuntime) -> None:
        self._runtime = runtime
        self._last_refreshed_at: Optional[str] = None

    @property
    def runtime(self) -> ContentRuntime:
        """The managed content runtime instance."""
        return self._runtime

    def get_state(self) -> RuntimeState:
        """Return the current runtime state without triggering a refresh."""
        courses = self._runtime.get_courses()
        return RuntimeState(
            courses_count=len(courses),
            last_refreshed_at=self._last_refreshed_at,
        )

    def refresh(self) -> RuntimeRefreshStats:
        """Reload published courses and return refresh statistics."""
        courses_before = len(self._runtime.get_courses())
        self._runtime.refresh()
        courses_after = len(self._runtime.get_courses())
        refreshed_at = _utc_timestamp()
        self._last_refreshed_at = refreshed_at
        return RuntimeRefreshStats(
            courses_before=courses_before,
            courses_after=courses_after,
            refreshed_at=refreshed_at,
            changed=courses_before != courses_after,
        )
