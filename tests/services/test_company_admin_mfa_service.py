"""Security contracts for encrypted tenant administrator MFA."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from app.database.db import get_connection, initialize_database
from app.repositories.user_mfa_repository import UserMFARepository
from app.services.company_admin_mfa_service import CompanyAdminMFAService
from app.web.mfa_secret_cipher import MFASecretCipher
from app.web.totp import code_for_counter, decode_base32_secret


class CompanyAdminMFAServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            self.user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('admin@example.com')"
                ).lastrowid
            )
        self.repository = UserMFARepository()
        self.clock_value = 59.0
        key = Fernet.generate_key().decode("ascii")
        self.service = CompanyAdminMFAService(
            self.repository,
            MFASecretCipher.from_environment(
                {"INTERTOP_MFA_ENCRYPTION_KEY": key}
            ),
            clock=lambda: self.clock_value,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_enrollment_secret_is_encrypted_and_login_code_cannot_replay(self) -> None:
        enrollment = self.service.begin_enrollment(
            self.db_path,
            user_id=self.user_id,
            email="admin@example.com",
        )
        stored = self.repository.get(self.db_path, self.user_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertNotIn(enrollment.secret, stored.encrypted_secret)
        self.assertFalse(stored.is_active)
        self.assertIn("otpauth://totp/", enrollment.authenticator_uri)

        secret = decode_base32_secret(enrollment.secret, field_name="test")
        first_code = code_for_counter(secret, 1)
        self.assertTrue(
            self.service.activate(
                self.db_path,
                user_id=self.user_id,
                code=first_code,
            )
        )

        self.clock_value = 90.0
        next_code = code_for_counter(secret, 3)
        self.assertTrue(
            self.service.verify_login(
                self.db_path,
                user_id=self.user_id,
                code=next_code,
            )
        )
        self.assertFalse(
            self.service.verify_login(
                self.db_path,
                user_id=self.user_id,
                code=next_code,
            )
        )

    def test_invalid_code_does_not_activate_pending_credential(self) -> None:
        self.service.begin_enrollment(
            self.db_path,
            user_id=self.user_id,
            email="admin@example.com",
        )

        self.assertFalse(
            self.service.activate(
                self.db_path,
                user_id=self.user_id,
                code="000000",
            )
        )
        self.assertFalse(self.service.is_enrolled(self.db_path, self.user_id))

    def test_missing_encryption_key_fails_closed(self) -> None:
        service = CompanyAdminMFAService(
            self.repository,
            MFASecretCipher.from_environment({}),
        )
        self.assertFalse(service.is_configured)
        with self.assertRaisesRegex(RuntimeError, "not configured"):
            service.begin_enrollment(
                self.db_path,
                user_id=self.user_id,
                email="admin@example.com",
            )

    def test_totp_verification_handles_start_of_unix_time(self) -> None:
        self.clock_value = 0.0
        enrollment = self.service.begin_enrollment(
            self.db_path,
            user_id=self.user_id,
            email="admin@example.com",
        )
        secret = decode_base32_secret(enrollment.secret, field_name="test")

        self.assertTrue(
            self.service.activate(
                self.db_path,
                user_id=self.user_id,
                code=code_for_counter(secret, 0),
            )
        )


if __name__ == "__main__":
    unittest.main()
