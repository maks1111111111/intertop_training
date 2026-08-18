"""Tests for cookie-backed Web session identity resolution."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.database.db import get_connection, initialize_database
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository
from app.services.tenant_context_service import TenantContextService
from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentityService
from app.web.web_session_config import WEB_SESSION_COOKIE_NAME
from app.web.web_session_service import WebSessionService


SECRET = "test-session-secret-key-with-at-least-32-bytes"


def _decode_payload(token: str) -> dict:
    encoded_payload = token.split(".", 1)[0]
    padding = "=" * (-len(encoded_payload) % 4)
    raw = base64.urlsafe_b64decode(
        (encoded_payload + padding).encode("ascii")
    )
    return json.loads(raw.decode("utf-8"))


class WebSessionIdentityTests(unittest.TestCase):
    """Verify get_current_web_identity reads and validates session cookies."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)

        self.session_service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )
        self.identity_service = WebIdentityService(
            UserRepository(),
            TenantContextService(
                CompanyRepository(),
                CompanyMembershipRepository(),
            ),
        )

        company_repository = CompanyRepository()
        company_repository.create(
            self.db_path,
            company_id="intertop",
            name="Intertop Retail",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _request_with_cookie(self, token: str | None) -> MagicMock:
        request = MagicMock()
        request.cookies.get.return_value = token
        return request

    def _create_password_only_user(self, *, role: str = "manager") -> int:
        with get_connection(self.db_path) as connection:
            user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name
                    )
                    VALUES (NULL, ?, ?, ?)
                    """,
                    ("web-only", "Web", "Only"),
                ).lastrowid
            )

        CompanyMembershipRepository().add(
            self.db_path,
            company_id="intertop",
            user_id=user_id,
            role=role,
        )
        return user_id

    def _resolve_identity(self, token: str | None):
        request = self._request_with_cookie(token)
        return get_current_web_identity(
            request,
            self.db_path,
            self.session_service,
            self.identity_service,
        )

    def test_missing_cookie_returns_no_identity(self) -> None:
        user_id = self._create_password_only_user()

        identity = self._resolve_identity(None)

        self.assertIsNone(identity)

    def test_missing_cookie_reads_configured_cookie_name(self) -> None:
        request = self._request_with_cookie(None)

        get_current_web_identity(
            request,
            self.db_path,
            self.session_service,
            self.identity_service,
        )

        request.cookies.get.assert_called_once_with(WEB_SESSION_COOKIE_NAME)

    def test_valid_signed_cookie_returns_canonical_identity(self) -> None:
        user_id = self._create_password_only_user(role="manager")
        token = self.session_service.create_token(
            user_id=user_id,
            company_id="intertop",
        )

        identity = self._resolve_identity(token)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_id, user_id)
        self.assertEqual(identity.company_id, "intertop")
        self.assertEqual(identity.company_name, "Intertop Retail")
        self.assertEqual(identity.role, "manager")

    def test_tampered_cookie_returns_no_identity(self) -> None:
        user_id = self._create_password_only_user()
        token = self.session_service.create_token(
            user_id=user_id,
            company_id="intertop",
        )
        encoded_payload, signature = token.split(".")

        payload = _decode_payload(token)
        payload["user_id"] = user_id + 999

        raw = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        tampered_payload = (
            base64.urlsafe_b64encode(raw)
            .decode("ascii")
            .rstrip("=")
        )
        tampered_token = f"{tampered_payload}.{signature}"

        self.assertNotEqual(tampered_payload, encoded_payload)
        self.assertIsNone(self._resolve_identity(tampered_token))

    def test_identity_works_for_canonical_user_without_telegram_id(self) -> None:
        user_id = self._create_password_only_user(role="student")
        token = self.session_service.create_token(
            user_id=user_id,
            company_id="intertop",
        )

        identity = self._resolve_identity(token)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_id, user_id)
        self.assertIsNone(identity.telegram_id)
        self.assertEqual(identity.role, "student")


if __name__ == "__main__":
    unittest.main()
