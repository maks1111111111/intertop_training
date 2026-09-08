"""Tests for the browser security header baseline."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.app import create_app


class SecurityHeadersTests(unittest.TestCase):
    def test_development_response_has_security_baseline_without_hsts(self) -> None:
        with patch.dict(os.environ, {"INTERTOP_ENV": "development"}, clear=True):
            response = TestClient(create_app()).get("/api/v1/health")

        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(
            response.headers["referrer-policy"],
            "strict-origin-when-cross-origin",
        )
        self.assertEqual(
            response.headers["permissions-policy"],
            "camera=(), microphone=(), geolocation=()",
        )
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertNotIn("strict-transport-security", response.headers)

    def test_production_response_enables_hsts(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "production",
                "INTERTOP_ALLOWED_HOSTS": "training.example.com",
                "WEB_SESSION_SECRET": "a-production-secret-that-is-long-enough",
            },
            clear=True,
        ):
            response = TestClient(create_app()).get(
                "/api/v1/health",
                headers={"host": "training.example.com"},
            )

        self.assertEqual(
            response.headers["strict-transport-security"],
            "max-age=31536000; includeSubDomains",
        )

    def test_rejected_host_response_still_has_security_headers(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "staging",
                "INTERTOP_ALLOWED_HOSTS": "training.example.com",
                "WEB_SESSION_SECRET": "a-staging-secret-that-is-long-enough",
            },
            clear=True,
        ):
            response = TestClient(create_app()).get(
                "/api/v1/health",
                headers={"host": "attacker.example"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("strict-transport-security", response.headers)
