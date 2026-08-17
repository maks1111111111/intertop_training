"""Tests for role-based Web authorization."""

from __future__ import annotations

import unittest

from app.web.web_authorization_service import WebAuthorizationService
from app.web.web_identity_service import WebIdentity


def _identity(role: str) -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=1001,
        company_id="company-a",
        company_name="Company A",
        role=role,
    )


class WebAuthorizationServiceTests(unittest.TestCase):
    """Verify authorization decisions use tenant membership roles."""

    def setUp(self) -> None:
        self.service = WebAuthorizationService()

    def test_student_cannot_manage_learning(self) -> None:
        self.assertFalse(self.service.can_manage_learning(_identity("student")))

    def test_manager_can_manage_learning(self) -> None:
        self.assertTrue(self.service.can_manage_learning(_identity("manager")))

    def test_admin_can_manage_learning(self) -> None:
        self.assertTrue(self.service.can_manage_learning(_identity("admin")))

    def test_unresolved_identity_cannot_manage_learning(self) -> None:
        self.assertFalse(self.service.can_manage_learning(None))

    def test_only_admin_passes_admin_check(self) -> None:
        self.assertFalse(self.service.is_admin(_identity("student")))
        self.assertFalse(self.service.is_admin(_identity("manager")))
        self.assertTrue(self.service.is_admin(_identity("admin")))

    def test_unresolved_identity_is_not_admin(self) -> None:
        self.assertFalse(self.service.is_admin(None))

    def test_has_role_supports_multiple_roles(self) -> None:
        self.assertTrue(
            self.service.has_role(
                _identity("manager"),
                ("manager", "admin"),
            )
        )

    def test_has_role_normalizes_allowed_roles(self) -> None:
        self.assertTrue(
            self.service.has_role(
                _identity("manager"),
                ("  Manager  ",),
            )
        )

    def test_empty_allowed_roles_returns_false(self) -> None:
        self.assertFalse(self.service.has_role(_identity("admin"), ()))

    def test_unknown_allowed_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.has_role(_identity("admin"), ("owner",))

    def test_non_string_allowed_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.has_role(_identity("admin"), ("admin", 1))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
