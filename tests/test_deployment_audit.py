"""Tests for the combined, read-only remote deployment preflight."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.database.db import get_connection, initialize_database
from app.deployment_audit import audit_deployment, format_report, run
from app.deployment_config import DeploymentConfig
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.runtime_paths_config import RuntimePathsConfig
from app.web_server import WebServerConfig


_SECURE_SECRET = "deployment-audit-session-secret-at-least-32-bytes"
_MFA_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class DeploymentAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_root = Path(self.tmp.name) / "state"
        self.db_path = self.state_root / "data" / "training.db"
        self.courses_dir = self.state_root / "courses"
        self.upload_dir = self.state_root / "uploads"
        self.courses_dir.mkdir(parents=True)
        self.upload_dir.mkdir()
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            owner_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('platform-owner')"
                ).lastrowid
            )
        PlatformAdminRepository().bootstrap_owner(self.db_path, owner_id)
        self.runtime_paths = RuntimePathsConfig(
            db_path=self.db_path,
            courses_dir=self.courses_dir,
            upload_dir=self.upload_dir,
        )
        self.config = DeploymentConfig(
            environment="staging",
            allowed_hosts=("staging.example.com",),
            force_secure_session_cookie=True,
        )
        self.web_server_config = WebServerConfig()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clean_remote_configuration_and_database_pass(self) -> None:
        report = audit_deployment(
            self.config,
            self.runtime_paths,
            self.web_server_config,
        )

        self.assertTrue(report.is_clean)
        self.assertEqual(
            format_report(report),
            "DEPLOYMENT_AUDIT\nenvironment=staging\nfindings=0\nstatus=clean",
        )

    def test_reports_non_loopback_listener_and_database_review(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute("DROP TRIGGER prevent_platform_audit_event_update")

        report = audit_deployment(
            self.config,
            self.runtime_paths,
            WebServerConfig(host="0.0.0.0"),
        )

        self.assertFalse(report.is_clean)
        self.assertEqual(
            {finding.code for finding in report.findings},
            {
                "web_listener_not_loopback",
                "platform.missing_platform_trigger",
            },
        )

    def test_configured_cli_returns_zero_for_clean_remote_state(self) -> None:
        environment = {
            "INTERTOP_ENV": "staging",
            "INTERTOP_ALLOWED_HOSTS": "staging.example.com",
            "WEB_SESSION_SECRET": _SECURE_SECRET,
            "INTERTOP_MFA_ENCRYPTION_KEY": _MFA_KEY,
            "INTERTOP_WEB_HOST": "127.0.0.1",
            "INTERTOP_WEB_PORT": "8000",
            "INTERTOP_FORWARDED_ALLOW_IPS": "127.0.0.1",
            "INTERTOP_DB_PATH": str(self.db_path),
            "INTERTOP_COURSES_DIR": str(self.courses_dir),
            "INTERTOP_UPLOAD_DIR": str(self.upload_dir),
        }
        stdout = io.StringIO()
        with patch("app.deployment_audit.load_project_env"), patch.dict(
            os.environ,
            environment,
            clear=True,
        ), redirect_stdout(stdout):
            exit_code = run()

        self.assertEqual(exit_code, 0)
        self.assertIn("status=clean", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
