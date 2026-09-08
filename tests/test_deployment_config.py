"""Tests for secure deployment profile validation."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.deployment_config import DeploymentConfig


_SECURE_SECRET = "test-deployment-session-secret-at-least-32-bytes"


class DeploymentConfigTests(unittest.TestCase):
    def test_development_defaults_remain_local_friendly(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = DeploymentConfig.from_environment()

        self.assertEqual(config.environment, "development")
        self.assertEqual(config.allowed_hosts, ("*",))
        self.assertFalse(config.force_secure_session_cookie)

    def test_production_requires_allowed_hosts(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "production",
                "WEB_SESSION_SECRET": _SECURE_SECRET,
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "INTERTOP_ALLOWED_HOSTS"):
                DeploymentConfig.from_environment()

    def test_production_rejects_wildcard_host(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "production",
                "INTERTOP_ALLOWED_HOSTS": "*",
                "WEB_SESSION_SECRET": _SECURE_SECRET,
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "must not contain"):
                DeploymentConfig.from_environment()

    def test_production_requires_valid_session_secret(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "production",
                "INTERTOP_ALLOWED_HOSTS": "training.example.com",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "WEB_SESSION_SECRET"):
                DeploymentConfig.from_environment()

    def test_production_rejects_example_session_secret(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "production",
                "INTERTOP_ALLOWED_HOSTS": "training.example.com",
                "WEB_SESSION_SECRET": (
                    "replace-with-a-random-secret-at-least-32-bytes"
                ),
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "example value"):
                DeploymentConfig.from_environment()

    def test_staging_normalizes_and_deduplicates_allowed_hosts(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_ENV": "STAGING",
                "INTERTOP_ALLOWED_HOSTS": (
                    "STAGING.example.com, staging.example.com, localhost"
                ),
                "WEB_SESSION_SECRET": _SECURE_SECRET,
            },
            clear=True,
        ):
            config = DeploymentConfig.from_environment()

        self.assertEqual(config.environment, "staging")
        self.assertEqual(
            config.allowed_hosts,
            ("staging.example.com", "localhost"),
        )
        self.assertTrue(config.force_secure_session_cookie)

    def test_unknown_environment_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"INTERTOP_ENV": "preview"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "INTERTOP_ENV"):
                DeploymentConfig.from_environment()

    def test_allowed_host_must_not_include_scheme_or_port(self) -> None:
        for invalid_host in (
            "https://training.example.com",
            "training.example.com:443",
        ):
            with self.subTest(invalid_host=invalid_host):
                with patch.dict(
                    os.environ,
                    {"INTERTOP_ALLOWED_HOSTS": invalid_host},
                    clear=True,
                ):
                    with self.assertRaisesRegex(RuntimeError, "invalid host"):
                        DeploymentConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
