"""Tests for the runtime refresh application service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.content.runtime_manager import (
    ContentRuntimeManager,
    RuntimeRefreshStats,
    RuntimeState,
)
from app.services.runtime_refresh_service import (
    RuntimeRefreshResult,
    RuntimeRefreshService,
)


class RuntimeRefreshServiceTests(unittest.TestCase):
    """Tests for :class:`RuntimeRefreshService`."""

    def test_refresh_calls_manager_refresh(self) -> None:
        manager = MagicMock(spec=ContentRuntimeManager)
        manager.refresh.return_value = RuntimeRefreshStats(
            courses_before=1,
            courses_after=2,
            refreshed_at="2026-07-30T18:00:00Z",
            changed=True,
        )
        service = RuntimeRefreshService(manager)

        service.refresh()

        manager.refresh.assert_called_once_with()

    def test_refresh_returns_correct_fields(self) -> None:
        manager = MagicMock(spec=ContentRuntimeManager)
        manager.refresh.return_value = RuntimeRefreshStats(
            courses_before=1,
            courses_after=2,
            refreshed_at="2026-07-30T18:00:00Z",
            changed=True,
        )
        service = RuntimeRefreshService(manager)

        result = service.refresh()

        self.assertIsInstance(result, RuntimeRefreshResult)
        self.assertEqual(result.courses_before, 1)
        self.assertEqual(result.courses_after, 2)
        self.assertTrue(result.changed)
        self.assertEqual(result.refreshed_at, "2026-07-30T18:00:00Z")

    def test_state_uses_manager_get_state(self) -> None:
        manager = MagicMock(spec=ContentRuntimeManager)
        expected_state = RuntimeState(
            courses_count=3,
            last_refreshed_at="2026-07-30T18:00:00Z",
        )
        manager.get_state.return_value = expected_state
        service = RuntimeRefreshService(manager)

        state = service.state()

        manager.get_state.assert_called_once_with()
        self.assertIs(state, expected_state)

    def test_state_does_not_call_refresh(self) -> None:
        manager = MagicMock(spec=ContentRuntimeManager)
        manager.get_state.return_value = RuntimeState(
            courses_count=0,
            last_refreshed_at=None,
        )
        service = RuntimeRefreshService(manager)

        service.state()

        manager.refresh.assert_not_called()

    def test_refresh_does_not_call_get_state(self) -> None:
        manager = MagicMock(spec=ContentRuntimeManager)
        manager.refresh.return_value = RuntimeRefreshStats(
            courses_before=0,
            courses_after=0,
            refreshed_at="2026-07-30T18:00:00Z",
            changed=False,
        )
        service = RuntimeRefreshService(manager)

        service.refresh()

        manager.get_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
