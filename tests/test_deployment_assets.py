"""Contracts for the checked-in one-VPS deployment templates."""

from __future__ import annotations

import unittest
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DeploymentAssetTests(unittest.TestCase):
    def test_systemd_service_runs_a_private_single_web_process(self) -> None:
        service = _read("deploy/systemd/intertop-training-web.service")

        self.assertIn("User=intertop", service)
        self.assertIn("EnvironmentFile=/etc/intertop-training/staging.env", service)
        self.assertIn("ExecStart=/opt/intertop-training/.venv/bin/python -m app.web_server", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ReadWritePaths=/srv/intertop-training", service)
        self.assertIn("NoNewPrivileges=yes", service)

    def test_tls_proxy_preserves_the_origin_scheme_and_private_backend(self) -> None:
        nginx = _read("deploy/nginx/intertop-training.conf.template")

        self.assertIn("server 127.0.0.1:8000", nginx)
        self.assertIn("proxy_set_header Host $host", nginx)
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme", nginx)
        self.assertIn("return 301 https://$host$request_uri", nginx)

    def test_backup_timer_uses_a_restricted_verified_backup_service(self) -> None:
        service = _read("deploy/systemd/intertop-training-backup.service")
        timer = _read("deploy/systemd/intertop-training-backup.timer")

        self.assertIn("User=intertop", service)
        self.assertIn("-m app.database.backup", service)
        self.assertIn("--output-dir /var/backups/intertop-training", service)
        self.assertIn("ReadWritePaths=/var/backups/intertop-training", service)
        self.assertIn("UMask=0077", service)
        self.assertIn("OnCalendar=*-*-* 03:15:00", timer)
        self.assertIn("Persistent=true", timer)

    def test_staging_environment_keeps_state_outside_the_checkout(self) -> None:
        environment = _read("deploy/staging.env.example")

        self.assertIn("INTERTOP_ENV=staging", environment)
        self.assertIn("INTERTOP_DB_PATH=/srv/intertop-training/data/training.db", environment)
        self.assertIn("INTERTOP_COURSES_DIR=/srv/intertop-training/courses", environment)
        self.assertIn("INTERTOP_UPLOAD_DIR=/srv/intertop-training/uploads", environment)
        self.assertNotIn("OPENAI_API_KEY=sk-", environment)


def _read(relative_path: str) -> str:
    return (_PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
