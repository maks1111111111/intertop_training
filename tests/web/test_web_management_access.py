"""Tests for Web management-access dependencies."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.database.db import initialize_database
from app.web.router import (
    get_current_web_identity,
    get_web_authorization_service,
    require_web_management_identity,
)
from app.web.web_authorization_service import WebAuthorizationService
from app.web.web_identity_service import WebIdentity, WebIdentityService


def _identity(role: str) -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=1,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class WebManagementAccessTests(unittest.TestCase):
    """Verify request-level management authorization fails closed."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_authorization_provider_returns_service(self) -> None:
        service = get_web_authorization_service()

        self.assertIsInstance(service, WebAuthorizationService)

    def test_current_identity_uses_web_identity_service(self) -> None:
        request = MagicMock()
        request.cookies.get.return_value = "signed-session"

        session_service = MagicMock()
        session_service.resolve_token.return_value = MagicMock(
            user_id=10,
            company_id="intertop",
        )

        fake_service = MagicMock(spec=WebIdentityService)
        expected = _identity("manager")
        fake_service.resolve_user.return_value = expected

        result = get_current_web_identity(
            request,
            self.db_path,
            session_service,
            fake_service,
        )

        self.assertEqual(result, expected)
        session_service.resolve_token.assert_called_once_with("signed-session")
        fake_service.resolve_user.assert_called_once_with(
            self.db_path,
            10,
            "intertop",
        )

    def test_current_identity_preserves_unresolved_state(self) -> None:
        request = MagicMock()
        request.cookies.get.return_value = "signed-session"

        session_service = MagicMock()
        session_service.resolve_token.return_value = MagicMock(
            user_id=10,
            company_id="intertop",
        )

        fake_service = MagicMock(spec=WebIdentityService)
        fake_service.resolve_user.return_value = None

        result = get_current_web_identity(
            request,
            self.db_path,
            session_service,
            fake_service,
        )

        self.assertIsNone(result)

    def test_manager_is_allowed(self) -> None:
        service = WebAuthorizationService()

        result = require_web_management_identity(_identity("manager"), service)

        self.assertEqual(result.role, "manager")

    def test_admin_is_allowed(self) -> None:
        service = WebAuthorizationService()

        result = require_web_management_identity(_identity("admin"), service)

        self.assertEqual(result.role, "admin")

    def test_student_is_denied_with_403(self) -> None:
        service = WebAuthorizationService()

        with self.assertRaises(HTTPException) as context:
            require_web_management_identity(_identity("student"), service)

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.detail, "Forbidden")

    def test_unresolved_identity_is_denied_with_403(self) -> None:
        service = WebAuthorizationService()

        with self.assertRaises(HTTPException) as context:
            require_web_management_identity(None, service)

        self.assertEqual(context.exception.status_code, 403)

    def test_denied_identity_is_not_returned(self) -> None:
        service = MagicMock(spec=WebAuthorizationService)
        service.can_manage_learning.return_value = False
        identity = _identity("manager")

        with self.assertRaises(HTTPException):
            require_web_management_identity(identity, service)

        service.can_manage_learning.assert_called_once_with(identity)


if __name__ == "__main__":
    unittest.main()
