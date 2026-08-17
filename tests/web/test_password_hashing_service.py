"""Tests for secure password hashing."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from pwdlib import PasswordHash

from app.web.password_hashing_service import (
    PasswordHashingService,
    PasswordVerificationResult,
)


class PasswordHashingServiceTests(unittest.TestCase):
    """Verify passwords are hashed and checked safely."""

    def setUp(self) -> None:
        self.service = PasswordHashingService()

    def test_hash_password_uses_argon2id(self) -> None:
        encoded = self.service.hash_password("correct horse battery staple")

        self.assertTrue(encoded.startswith("$argon2id$"))

    def test_hash_password_is_not_plaintext(self) -> None:
        password = "Intertop-Strong-Password-123!"

        encoded = self.service.hash_password(password)

        self.assertNotEqual(encoded, password)
        self.assertNotIn(password, encoded)

    def test_same_password_gets_different_salted_hashes(self) -> None:
        first = self.service.hash_password("same-password")
        second = self.service.hash_password("same-password")

        self.assertNotEqual(first, second)

    def test_correct_password_verifies(self) -> None:
        encoded = self.service.hash_password("correct-password")

        result = self.service.verify_password("correct-password", encoded)

        self.assertIsInstance(result, PasswordVerificationResult)
        self.assertTrue(result.valid)

    def test_wrong_password_is_rejected(self) -> None:
        encoded = self.service.hash_password("correct-password")

        result = self.service.verify_password("wrong-password", encoded)

        self.assertFalse(result.valid)
        self.assertIsNone(result.updated_hash)

    def test_malformed_hash_fails_closed(self) -> None:
        result = self.service.verify_password(
            "password",
            "not-a-valid-password-hash",
        )

        self.assertFalse(result.valid)
        self.assertIsNone(result.updated_hash)

    def test_verify_and_update_replacement_hash_is_returned(self) -> None:
        fake = MagicMock(spec=PasswordHash)
        fake.verify_and_update.return_value = (
            True,
            "$argon2id$v=19$updated-hash",
        )
        service = PasswordHashingService(fake)

        result = service.verify_password(
            "password",
            "$argon2id$v=19$old-hash",
        )

        self.assertTrue(result.valid)
        self.assertEqual(
            result.updated_hash,
            "$argon2id$v=19$updated-hash",
        )

    def test_verify_without_rehash_returns_none_updated_hash(self) -> None:
        fake = MagicMock(spec=PasswordHash)
        fake.verify_and_update.return_value = (True, None)
        service = PasswordHashingService(fake)

        result = service.verify_password(
            "password",
            "$argon2id$v=19$current-hash",
        )

        self.assertTrue(result.valid)
        self.assertIsNone(result.updated_hash)

    def test_hash_delegates_plaintext_only_to_hashing_library(self) -> None:
        fake = MagicMock(spec=PasswordHash)
        fake.hash.return_value = "$argon2id$v=19$hash"
        service = PasswordHashingService(fake)

        result = service.hash_password("secret-password")

        self.assertEqual(result, "$argon2id$v=19$hash")
        fake.hash.assert_called_once_with("secret-password")

    def test_empty_password_is_rejected(self) -> None:
        for password in ("", b""):
            with self.subTest(password=password):
                with self.assertRaises(ValueError):
                    self.service.hash_password(password)

    def test_non_string_password_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.hash_password(123)  # type: ignore[arg-type]

    def test_empty_hash_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.verify_password("password", "   ")

    def test_non_string_hash_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.verify_password(
                "password",
                123,  # type: ignore[arg-type]
            )

    def test_library_verification_error_fails_closed(self) -> None:
        fake = MagicMock(spec=PasswordHash)
        fake.verify_and_update.side_effect = RuntimeError("verification failed")
        service = PasswordHashingService(fake)

        result = service.verify_password(
            "password",
            "$argon2id$v=19$stored",
        )

        self.assertFalse(result.valid)
        self.assertIsNone(result.updated_hash)


if __name__ == "__main__":
    unittest.main()
