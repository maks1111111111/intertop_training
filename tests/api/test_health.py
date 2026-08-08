"""Tests for the versioned health endpoint."""

from __future__ import annotations

import unittest

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
