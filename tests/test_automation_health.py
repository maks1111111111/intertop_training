"""Tests for daily automation freshness markers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.automation_health import automation_is_healthy


class AutomationHealthTests(unittest.TestCase):
    def test_returns_healthy_when_all_markers_are_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health_dir = Path(tmp)
            for marker_name in ("audit-success", "offsite-backup-success"):
                marker = health_dir / marker_name
                marker.touch()
                os.utime(marker, (900.0, 900.0))

            self.assertTrue(
                automation_is_healthy(
                    now=1_000.0,
                    health_dir=health_dir,
                    max_age_seconds=200,
                )
            )

    def test_returns_unhealthy_when_marker_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health_dir = Path(tmp)
            (health_dir / "audit-success").touch()

            self.assertFalse(
                automation_is_healthy(
                    now=1_000.0,
                    health_dir=health_dir,
                    max_age_seconds=200,
                )
            )

    def test_returns_unhealthy_when_marker_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health_dir = Path(tmp)
            for marker_name in ("audit-success", "offsite-backup-success"):
                marker = health_dir / marker_name
                marker.touch()
                os.utime(marker, (700.0, 700.0))

            self.assertFalse(
                automation_is_healthy(
                    now=1_000.0,
                    health_dir=health_dir,
                    max_age_seconds=200,
                )
            )

    def test_returns_unhealthy_for_future_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health_dir = Path(tmp)
            for marker_name in ("audit-success", "offsite-backup-success"):
                marker = health_dir / marker_name
                marker.touch()
                os.utime(marker, (1_100.0, 1_100.0))

            self.assertFalse(
                automation_is_healthy(
                    now=1_000.0,
                    health_dir=health_dir,
                    max_age_seconds=200,
                )
            )


if __name__ == "__main__":
    unittest.main()
