"""Tests for tenant password lifecycle operations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.password_credential_repository import PasswordCredentialRepository
from app.services.user_password_service import UserPasswordError, UserPasswordService
from app.web.password_hashing_service import PasswordVerificationResult


class _FakePasswordHashingService:
    def hash_password(self, password: str) -> str:
        return f"hash:{password}"

    def verify_password(self, password: str, password_hash: str) -> PasswordVerificationResult:
        return PasswordVerificationResult(valid=password_hash == f"hash:{password}")


class UserPasswordServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = PasswordCredentialRepository()
        self.service = UserPasswordService(
            self.repository,
            _FakePasswordHashingService(),  # type: ignore[arg-type]
        )
        with get_connection(self.db_path) as connection:
            self.actor_id = int(
                connection.execute("INSERT INTO users (username) VALUES ('actor')").lastrowid
            )
            self.target_id = int(
                connection.execute("INSERT INTO users (username) VALUES ('target')").lastrowid
            )
        self.repository.create(
            self.db_path,
            user_id=self.actor_id,
            email="actor@example.com",
            password_hash="hash:Actor-password-1",
        )
        self.repository.create(
            self.db_path,
            user_id=self.target_id,
            email="target@example.com",
            password_hash="hash:Temporary-123",
            must_change_password=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_login_change_clears_requirement(self) -> None:
        self.service.change_password(
            self.db_path,
            user_id=self.target_id,
            current_password="Temporary-123",
            new_password="Permanent-456",
            confirmation="Permanent-456",
        )
        credential = self.repository.get_by_user_id(self.db_path, self.target_id)
        self.assertIsNotNone(credential)
        assert credential is not None
        self.assertEqual(credential.password_hash, "hash:Permanent-456")
        self.assertFalse(credential.must_change_password)

    def test_change_rejects_wrong_current_password(self) -> None:
        with self.assertRaisesRegex(UserPasswordError, "неверно"):
            self.service.change_password(
                self.db_path,
                user_id=self.target_id,
                current_password="wrong",
                new_password="Permanent-456",
                confirmation="Permanent-456",
            )

    def test_reset_requires_actor_password_and_marks_temporary(self) -> None:
        self.service.reset_to_temporary_password(
            self.db_path,
            actor_user_id=self.actor_id,
            actor_password="Actor-password-1",
            user_id=self.target_id,
            temporary_password="Another-temp-9",
            confirmation="Another-temp-9",
        )
        credential = self.repository.get_by_user_id(self.db_path, self.target_id)
        self.assertIsNotNone(credential)
        assert credential is not None
        self.assertEqual(credential.password_hash, "hash:Another-temp-9")
        self.assertTrue(credential.must_change_password)


if __name__ == "__main__":
    unittest.main()
