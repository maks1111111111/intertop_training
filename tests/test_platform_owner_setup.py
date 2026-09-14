"""Contracts for securely provisioning the first platform owner."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app.database.db import get_connection
from app.platform_owner_setup import create_initial_platform_owner, main
from app.web.password_hashing_service import PasswordHashingService


class PlatformOwnerSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_creates_credential_backed_owner_with_normalized_email(self) -> None:
        user_id = create_initial_platform_owner(
            self.db_path,
            email=" Owner@Example.COM ",
            password="Strong-password-123!",
        )

        with get_connection(self.db_path) as connection:
            credential = connection.execute(
                "SELECT email, password_hash FROM user_password_credentials"
            ).fetchone()
            owner = connection.execute(
                "SELECT user_id, is_owner, is_active FROM platform_admins"
            ).fetchone()
            audit = connection.execute(
                "SELECT action, reason FROM platform_audit_events"
            ).fetchone()

        self.assertEqual(credential["email"], "owner@example.com")
        self.assertNotIn("Strong-password-123!", credential["password_hash"])
        self.assertTrue(
            PasswordHashingService()
            .verify_password("Strong-password-123!", credential["password_hash"])
            .valid
        )
        self.assertEqual(owner["user_id"], user_id)
        self.assertEqual((owner["is_owner"], owner["is_active"]), (1, 1))
        self.assertEqual(
            (audit["action"], audit["reason"]),
            ("platform_admin.bootstrap_owner", "setup_cli"),
        )

    def test_refuses_second_platform_administrator_without_creating_credential(self) -> None:
        create_initial_platform_owner(
            self.db_path,
            email="owner@example.com",
            password="Strong-password-123!",
        )

        with self.assertRaisesRegex(RuntimeError, "already exists"):
            create_initial_platform_owner(
                self.db_path,
                email="second@example.com",
                password="Strong-password-456!",
            )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM user_password_credentials"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_cli_keeps_password_out_of_output_and_requires_confirmation(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with patch("builtins.input", return_value="owner@example.com"), patch(
            "app.platform_owner_setup.getpass.getpass",
            side_effect=("Strong-password-123!", "Strong-password-123!"),
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["--db", str(self.db_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("user_id=1", stdout.getvalue())
        self.assertNotIn("Strong-password-123!", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_rejects_mismatched_password_without_creating_database(self) -> None:
        stderr = StringIO()
        with patch("builtins.input", return_value="owner@example.com"), patch(
            "app.platform_owner_setup.getpass.getpass",
            side_effect=("Strong-password-123!", "Different-password-123!"),
        ), redirect_stderr(stderr):
            exit_code = main(["--db", str(self.db_path)])

        self.assertEqual(exit_code, 2)
        self.assertIn("confirmation", stderr.getvalue())
        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
