"""Tests for password credential persistence."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.password_credential_repository import (
    PasswordCredential,
    PasswordCredentialRepository,
)


class PasswordCredentialRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = PasswordCredentialRepository()

        with get_connection(self.db_path) as connection:
            self.user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES (?)",
                    ("web-user",),
                ).lastrowid
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_and_get_by_email(self) -> None:
        created = self.repository.create(
            self.db_path,
            user_id=self.user_id,
            email="User@Example.COM",
            password_hash="hashed-value",
        )

        self.assertIsInstance(created, PasswordCredential)
        self.assertEqual(created.user_id, self.user_id)
        self.assertEqual(created.email, "user@example.com")
        self.assertEqual(created.password_hash, "hashed-value")
        self.assertTrue(created.is_active)

        loaded = self.repository.get_by_email(
            self.db_path,
            " USER@example.com ",
        )

        self.assertEqual(loaded, created)

    def test_get_by_user_id(self) -> None:
        created = self.repository.create(
            self.db_path,
            user_id=self.user_id,
            email="user@example.com",
            password_hash="hash",
        )

        loaded = self.repository.get_by_user_id(
            self.db_path,
            self.user_id,
        )

        self.assertEqual(loaded, created)

    def test_unknown_email_returns_none(self) -> None:
        self.assertIsNone(
            self.repository.get_by_email(
                self.db_path,
                "missing@example.com",
            )
        )

    def test_unknown_user_returns_none(self) -> None:
        self.assertIsNone(
            self.repository.get_by_user_id(
                self.db_path,
                999999,
            )
        )

    def test_duplicate_email_case_insensitive_rejected(self) -> None:
        self.repository.create(
            self.db_path,
            user_id=self.user_id,
            email="User@example.com",
            password_hash="hash-one",
        )

        with get_connection(self.db_path) as connection:
            second_user = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES (?)",
                    ("second",),
                ).lastrowid
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create(
                self.db_path,
                user_id=second_user,
                email="user@EXAMPLE.com",
                password_hash="hash-two",
            )

    def test_duplicate_user_rejected(self) -> None:
        self.repository.create(
            self.db_path,
            user_id=self.user_id,
            email="first@example.com",
            password_hash="hash-one",
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create(
                self.db_path,
                user_id=self.user_id,
                email="second@example.com",
                password_hash="hash-two",
            )

    def test_invalid_user_ids_rejected(self) -> None:
        for invalid in (0, -1, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.repository.get_by_user_id(
                        self.db_path,
                        invalid,
                    )

    def test_empty_email_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.create(
                self.db_path,
                user_id=self.user_id,
                email="   ",
                password_hash="hash",
            )

    def test_empty_password_hash_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.create(
                self.db_path,
                user_id=self.user_id,
                email="user@example.com",
                password_hash="  ",
            )

    def test_update_password_hash(self) -> None:
        self.repository.create(
            self.db_path,
            user_id=self.user_id,
            email="user@example.com",
            password_hash="old-hash",
        )

        self.assertTrue(
            self.repository.update_password_hash(
                self.db_path,
                self.user_id,
                "new-hash",
            )
        )

        loaded = self.repository.get_by_user_id(
            self.db_path,
            self.user_id,
        )
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.password_hash, "new-hash")

    def test_update_unknown_user_returns_false(self) -> None:
        self.assertFalse(
            self.repository.update_password_hash(
                self.db_path,
                999999,
                "hash",
            )
        )

    def test_set_active(self) -> None:
        self.repository.create(
            self.db_path,
            user_id=self.user_id,
            email="user@example.com",
            password_hash="hash",
        )

        self.assertTrue(
            self.repository.set_active(
                self.db_path,
                self.user_id,
                False,
            )
        )

        loaded = self.repository.get_by_user_id(
            self.db_path,
            self.user_id,
        )
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertFalse(loaded.is_active)


if __name__ == "__main__":
    unittest.main()
