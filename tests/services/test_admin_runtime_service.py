"""Tests for the admin runtime application service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.admin_runtime_service import AdminRuntimeService
from app.services.runtime_refresh_service import (
    RuntimeRefreshResult,
    RuntimeRefreshService,
)


class AdminRuntimeServiceTests(unittest.TestCase):
    """Tests for :class:`AdminRuntimeService`."""

    def test_refresh_runtime_calls_refresh_service_refresh(self) -> None:
        refresh_service = MagicMock(spec=RuntimeRefreshService)
        refresh_service.refresh.return_value = RuntimeRefreshResult(
            courses_before=1,
            courses_after=2,
            changed=True,
            refreshed_at="2026-07-30T18:00:00Z",
        )
        admin_service = AdminRuntimeService(refresh_service)

        admin_service.refresh_runtime()

        refresh_service.refresh.assert_called_once_with()

    def test_refresh_runtime_returns_same_result(self) -> None:
        refresh_service = MagicMock(spec=RuntimeRefreshService)
        expected_result = RuntimeRefreshResult(
            courses_before=1,
            courses_after=2,
            changed=True,
            refreshed_at="2026-07-30T18:00:00Z",
        )
        refresh_service.refresh.return_value = expected_result
        admin_service = AdminRuntimeService(refresh_service)

        result = admin_service.refresh_runtime()

        self.assertIs(result, expected_result)

    def test_refresh_runtime_does_not_call_state(self) -> None:
        refresh_service = MagicMock(spec=RuntimeRefreshService)
        refresh_service.refresh.return_value = RuntimeRefreshResult(
            courses_before=0,
            courses_after=0,
            changed=False,
            refreshed_at="2026-07-30T18:00:00Z",
        )
        admin_service = AdminRuntimeService(refresh_service)

        admin_service.refresh_runtime()

        refresh_service.state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
