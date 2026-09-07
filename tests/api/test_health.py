"""Tests for the versioned health endpoint."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.app import create_app


class HealthEndpointTests(unittest.TestCase):
    """Verify the /api/v1/health contract."""

    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_returns_200(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)

    def test_health_returns_expected_json(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_is_under_api_v1_prefix(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)

    def test_unversioned_health_is_not_available(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 404)

    def test_readiness_returns_200_when_database_is_available(self) -> None:
        response = self.client.get("/api/v1/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})

    @patch(
        "app.api.v1.health.get_connection",
        side_effect=sqlite3.OperationalError("database is locked"),
    )
    def test_readiness_returns_503_when_database_is_unavailable(
        self,
        _mock_get_connection,
    ) -> None:
        response = self.client.get("/api/v1/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Service unavailable"})

    def test_readiness_returns_503_without_creating_missing_database(self) -> None:
        original_db_path = self.client.app.state.db_path
        with tempfile.TemporaryDirectory() as tmp:
            missing_db_path = Path(tmp) / "missing.db"
            try:
                self.client.app.state.db_path = missing_db_path

                response = self.client.get("/api/v1/ready")
            finally:
                self.client.app.state.db_path = original_db_path

            self.assertEqual(response.status_code, 503)
            self.assertFalse(missing_db_path.exists())

    @patch(
        "app.api.v1.health.get_connection",
        side_effect=sqlite3.OperationalError("database is locked"),
    )
    def test_liveness_remains_healthy_when_readiness_fails(
        self,
        _mock_get_connection,
    ) -> None:
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
