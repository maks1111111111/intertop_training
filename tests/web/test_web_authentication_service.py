"""Tests for password-based Web authentication."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.database.db import get_connection, initialize_database
from app.repositories.company_membership_repository import (
    CompanyMembershipRepository,
)
from app.repositories.company_repository import CompanyRepository
from app.repositories.password_credential_repository import (
    PasswordCredentialRepository,
)
from app.repositories.user_repository import UserRepository
from app.services.tenant_context_service import TenantContextService
from app.web.password_hashing_service import (
    PasswordHashingService,
    PasswordVerificationResult,
)
from app.web.web_authentication_service import WebAuthenticationService
from app.web.web_identity_service import WebIdentityService


class WebAuthenticationServiceTests(unittest.TestCase):
    """Verify credentials resolve only active tenant-scoped identities."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)

        self.company_repository = CompanyRepository()
        self.membership_repository = CompanyMembershipRepository()
        self.credential_repository = PasswordCredentialRepository()
        self.password_hashing_service = PasswordHashingService()

        self.identity_service = WebIdentityService(
            UserRepository(),
            TenantContextService(
                self.company_repository,
                self.membership_repository,
            ),
        )

        self.service = WebAuthenticationService(
            self.credential_repository,
            self.password_hashing_service,
            self.identity_service,
        )

        self.company_repository.create(
            self.db_path,
            company_id="intertop",
            name="Intertop Retail",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user(
        self,
        *,
        email: str = "user@example.com",
        password: str = "Strong-password-123!",
        role: str = "student",
        user_active: bool = True,
        credential_active: bool = True,
        membership_active: bool = True,
    ) -> int:
        with get_connection(self.db_path) as connection:
            user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name,
                        is_active
                    )
                    VALUES (NULL, ?, ?, ?, ?)
                    """,
                    (
                        "web-only",
                        "Web",
                        "User",
                        1 if user_active else 0,
                    ),
                ).lastrowid
            )

        self.membership_repository.add(
            self.db_path,
            company_id="intertop",
            user_id=user_id,
            role=role,
        )

        if not membership_active:
            self.membership_repository.set_active(
                self.db_path,
                "intertop",
                user_id,
                False,
            )

        password_hash = self.password_hashing_service.hash_password(password)
        self.credential_repository.create(
            self.db_path,
            user_id=user_id,
            email=email,
            password_hash=password_hash,
        )

        if not credential_active:
            self.credential_repository.set_active(
                self.db_path,
                user_id,
                False,
            )

        return user_id

    def test_valid_password_only_user_authenticates(self) -> None:
        user_id = self._create_user(role="manager")

        identity = self.service.authenticate(
            self.db_path,
            email=" USER@example.com ",
            password="Strong-password-123!",
            company_id="intertop",
        )

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_id, user_id)
        self.assertIsNone(identity.telegram_id)
        self.assertEqual(identity.company_id, "intertop")
        self.assertEqual(identity.role, "manager")

    def test_wrong_password_returns_none(self) -> None:
        self._create_user()

        identity = self.service.authenticate(
            self.db_path,
            email="user@example.com",
            password="wrong-password",
            company_id="intertop",
        )

        self.assertIsNone(identity)

    def test_unknown_email_returns_none(self) -> None:
        identity = self.service.authenticate(
            self.db_path,
            email="missing@example.com",
            password="some-password",
            company_id="intertop",
        )

        self.assertIsNone(identity)

    def test_empty_email_returns_none(self) -> None:
        self.assertIsNone(
            self.service.authenticate(
                self.db_path,
                email="   ",
                password="password",
                company_id="intertop",
            )
        )

    def test_empty_password_returns_none(self) -> None:
        self._create_user()

        self.assertIsNone(
            self.service.authenticate(
                self.db_path,
                email="user@example.com",
                password="",
                company_id="intertop",
            )
        )

    def test_inactive_credential_returns_none(self) -> None:
        self._create_user(credential_active=False)

        identity = self.service.authenticate(
            self.db_path,
            email="user@example.com",
            password="Strong-password-123!",
            company_id="intertop",
        )

        self.assertIsNone(identity)

    def test_inactive_user_returns_none(self) -> None:
        self._create_user(user_active=False)

        identity = self.service.authenticate(
            self.db_path,
            email="user@example.com",
            password="Strong-password-123!",
            company_id="intertop",
        )

        self.assertIsNone(identity)

    def test_inactive_membership_returns_none(self) -> None:
        self._create_user(membership_active=False)

        identity = self.service.authenticate(
            self.db_path,
            email="user@example.com",
            password="Strong-password-123!",
            company_id="intertop",
        )

        self.assertIsNone(identity)

    def test_inactive_company_returns_none(self) -> None:
        self._create_user()
        self.company_repository.set_active(
            self.db_path,
            "intertop",
            False,
        )

        identity = self.service.authenticate(
            self.db_path,
            email="user@example.com",
            password="Strong-password-123!",
            company_id="intertop",
        )

        self.assertIsNone(identity)

    def test_wrong_company_returns_none(self) -> None:
        self._create_user()

        identity = self.service.authenticate(
            self.db_path,
            email="user@example.com",
            password="Strong-password-123!",
            company_id="another-company",
        )

        self.assertIsNone(identity)

    def test_unknown_email_uses_dummy_password_verification(self) -> None:
        credential_repository = MagicMock(spec=PasswordCredentialRepository)
        hashing_service = MagicMock(spec=PasswordHashingService)
        identity_service = MagicMock(spec=WebIdentityService)

        credential_repository.get_by_email.return_value = None
        hashing_service.verify_password.return_value = PasswordVerificationResult(
            valid=False
        )

        service = WebAuthenticationService(
            credential_repository,
            hashing_service,
            identity_service,
            dummy_password_hash="$argon2id$dummy",
        )

        result = service.authenticate(
            self.db_path,
            email="missing@example.com",
            password="candidate-password",
            company_id="intertop",
        )

        self.assertIsNone(result)
        hashing_service.verify_password.assert_called_once_with(
            "candidate-password",
            "$argon2id$dummy",
        )
        identity_service.resolve_user.assert_not_called()

    def test_rehash_is_persisted_after_successful_authentication(self) -> None:
        user_id = self._create_user()

        hashing_service = MagicMock(spec=PasswordHashingService)
        hashing_service.verify_password.return_value = PasswordVerificationResult(
            valid=True,
            updated_hash="$argon2id$replacement",
        )

        service = WebAuthenticationService(
            self.credential_repository,
            hashing_service,
            self.identity_service,
            dummy_password_hash="$argon2id$dummy",
        )

        identity = service.authenticate(
            self.db_path,
            email="user@example.com",
            password="Strong-password-123!",
            company_id="intertop",
        )

        self.assertIsNotNone(identity)

        credential = self.credential_repository.get_by_user_id(
            self.db_path,
            user_id,
        )
        self.assertIsNotNone(credential)
        assert credential is not None
        self.assertEqual(
            credential.password_hash,
            "$argon2id$replacement",
        )

    def test_invalid_company_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.authenticate(
                self.db_path,
                email="user@example.com",
                password="password",
                company_id="   ",
            )


if __name__ == "__main__":
    unittest.main()
