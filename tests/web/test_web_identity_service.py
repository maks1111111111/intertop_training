"""Tests for WebIdentityService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository
from app.services.tenant_context_service import (
    TenantContextService,
    TenantUserContext,
)
from app.web.web_identity_service import WebIdentity, WebIdentityService


class WebIdentityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.user_repository = UserRepository()
        self.company_repository = CompanyRepository()
        self.membership_repository = CompanyMembershipRepository()
        self.tenant_context_service = TenantContextService(
            self.company_repository,
            self.membership_repository,
        )
        self.service = WebIdentityService(
            self.user_repository,
            self.tenant_context_service,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_company(
        self,
        company_id: str,
        name: str,
        *,
        active: bool = True,
    ) -> None:
        self.company_repository.create(self.db_path, company_id=company_id, name=name)
        if not active:
            self.company_repository.set_active(self.db_path, company_id, False)

    def _create_user(
        self,
        telegram_id: int = 1001,
        *,
        active: bool = True,
        global_role: str = "student",
    ) -> int:
        upsert_telegram_user(
            self.db_path,
            telegram_id=telegram_id,
            username=f"user{telegram_id}",
            first_name="Test",
            last_name="User",
        )
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                UPDATE users
                SET role = ?, is_active = ?
                WHERE telegram_id = ?
                """,
                (global_role, 1 if active else 0, telegram_id),
            )
            row = connection.execute(
                """
                SELECT id
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        return int(row["id"])

    def _add_membership(
        self,
        company_id: str,
        user_id: int,
        role: str = "student",
        *,
        active: bool = True,
    ) -> None:
        self.membership_repository.add(
            self.db_path,
            company_id=company_id,
            user_id=user_id,
            role=role,
        )
        if not active:
            self.membership_repository.set_active(
                self.db_path,
                company_id,
                user_id,
                False,
            )

    def _count_rows(self, table: str) -> int:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM {table}"
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        return int(row["count"])

    def test_resolve_student_identity(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=2001)
        self._add_membership("intertop", user_id, role="student")

        identity = self.service.resolve(self.db_path, 2001, "intertop")

        self.assertIsInstance(identity, WebIdentity)
        assert identity is not None
        self.assertEqual(identity.role, "student")

    def test_resolve_manager_identity(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=2002)
        self._add_membership("intertop", user_id, role="manager")

        identity = self.service.resolve(self.db_path, 2002, "intertop")

        assert identity is not None
        self.assertEqual(identity.role, "manager")

    def test_resolve_admin_identity(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=2003)
        self._add_membership("intertop", user_id, role="admin")

        identity = self.service.resolve(self.db_path, 2003, "intertop")

        assert identity is not None
        self.assertEqual(identity.role, "admin")

    def test_resolve_returns_expected_fields(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3001)
        self._add_membership("intertop", user_id, role="manager")

        identity = self.service.resolve(self.db_path, 3001, "intertop")

        assert identity is not None
        self.assertEqual(identity.user_id, user_id)
        self.assertEqual(identity.telegram_id, 3001)
        self.assertEqual(identity.company_id, "intertop")
        self.assertEqual(identity.company_name, "Intertop Retail")
        self.assertEqual(identity.role, "manager")

    def test_resolve_strips_company_id(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3002)
        self._add_membership("intertop", user_id)

        identity = self.service.resolve(self.db_path, 3002, "  intertop  ")

        assert identity is not None
        self.assertEqual(identity.company_id, "intertop")

    def test_unknown_telegram_user_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")

        self.assertIsNone(self.service.resolve(self.db_path, 9999, "intertop"))

    def test_inactive_user_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3003, active=False)
        self._add_membership("intertop", user_id)

        self.assertIsNone(self.service.resolve(self.db_path, 3003, "intertop"))

    def test_missing_company_returns_none(self) -> None:
        self._create_user(telegram_id=3004)

        self.assertIsNone(self.service.resolve(self.db_path, 3004, "missing-company"))

    def test_inactive_company_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail", active=False)
        user_id = self._create_user(telegram_id=3005)
        self._add_membership("intertop", user_id)

        self.assertIsNone(self.service.resolve(self.db_path, 3005, "intertop"))

    def test_missing_membership_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        self._create_user(telegram_id=3006)

        self.assertIsNone(self.service.resolve(self.db_path, 3006, "intertop"))

    def test_inactive_membership_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3007)
        self._add_membership("intertop", user_id, active=False)

        self.assertIsNone(self.service.resolve(self.db_path, 3007, "intertop"))

    def test_same_user_resolves_different_roles_in_two_companies(self) -> None:
        self._create_company("company-a", "Company A")
        self._create_company("company-b", "Company B")
        user_id = self._create_user(telegram_id=3008)
        self._add_membership("company-a", user_id, role="student")
        self._add_membership("company-b", user_id, role="admin")

        identity_a = self.service.resolve(self.db_path, 3008, "company-a")
        identity_b = self.service.resolve(self.db_path, 3008, "company-b")

        assert identity_a is not None
        assert identity_b is not None
        self.assertEqual(identity_a.role, "student")
        self.assertEqual(identity_b.role, "admin")

    def test_resolve_user_supports_password_only_user(self) -> None:
        self._create_company("intertop", "Intertop Retail")

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

        self._add_membership(
            "intertop",
            user_id,
            role="manager",
        )

        identity = self.service.resolve_user(
            self.db_path,
            user_id,
            "intertop",
        )

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_id, user_id)
        self.assertIsNone(identity.telegram_id)
        self.assertEqual(identity.company_id, "intertop")
        self.assertEqual(identity.role, "manager")

    def test_resolve_user_existing_telegram_user_preserves_telegram_id(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3013)
        self._add_membership("intertop", user_id, role="student")

        identity = self.service.resolve_user(
            self.db_path,
            user_id,
            "intertop",
        )

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_id, user_id)
        self.assertEqual(identity.telegram_id, 3013)

    def test_resolve_user_unknown_user_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")

        self.assertIsNone(
            self.service.resolve_user(
                self.db_path,
                999999,
                "intertop",
            )
        )

    def test_resolve_user_inactive_user_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3014, active=False)
        self._add_membership("intertop", user_id)

        self.assertIsNone(
            self.service.resolve_user(
                self.db_path,
                user_id,
                "intertop",
            )
        )

    def test_resolve_user_missing_membership_returns_none(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3015)

        self.assertIsNone(
            self.service.resolve_user(
                self.db_path,
                user_id,
                "intertop",
            )
        )

    def test_resolve_user_invalid_ids_rejected(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.service.resolve_user(
                        self.db_path,
                        invalid,  # type: ignore[arg-type]
                        "intertop",
                    )

    def test_membership_role_overrides_global_users_role(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user(telegram_id=3009, global_role="admin")
        self._add_membership("intertop", user_id, role="student")

        identity = self.service.resolve(self.db_path, 3009, "intertop")

        assert identity is not None
        self.assertEqual(identity.role, "student")

    def test_zero_telegram_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, 0, "intertop")

    def test_negative_telegram_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, -1, "intertop")

    def test_bool_telegram_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, True, "intertop")

    def test_non_int_telegram_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, "1001", "intertop")  # type: ignore[arg-type]

    def test_empty_company_id_rejected(self) -> None:
        self._create_user(telegram_id=3010)

        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, 3010, "")

    def test_whitespace_only_company_id_rejected(self) -> None:
        self._create_user(telegram_id=3011)

        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, 3011, "   ")

    def test_non_string_company_id_rejected(self) -> None:
        self._create_user(telegram_id=3012)

        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, 3012, 123)  # type: ignore[arg-type]

    def test_resolve_does_not_create_users_companies_or_memberships(self) -> None:
        users_before = self._count_rows("users")
        companies_before = self._count_rows("companies")
        memberships_before = self._count_rows("company_memberships")

        self.assertIsNone(self.service.resolve(self.db_path, 7777, "missing-company"))

        self.assertEqual(self._count_rows("users"), users_before)
        self.assertEqual(self._count_rows("companies"), companies_before)
        self.assertEqual(self._count_rows("company_memberships"), memberships_before)

    def test_injected_dependencies_are_used(self) -> None:
        user_repository = MagicMock()
        tenant_context_service = MagicMock()
        user_row = {
            "id": 42,
            "telegram_id": 5001,
            "is_active": 1,
        }
        user_repository.get_by_telegram_id.return_value = user_row
        tenant_context_service.resolve.return_value = TenantUserContext(
            user_id=42,
            company_id="intertop",
            company_name="Intertop Retail",
            role="manager",
        )

        service = WebIdentityService(user_repository, tenant_context_service)
        identity = service.resolve(self.db_path, 5001, "intertop")

        user_repository.get_by_telegram_id.assert_called_once_with(self.db_path, 5001)
        tenant_context_service.resolve.assert_called_once_with(
            self.db_path,
            42,
            "intertop",
        )
        assert identity is not None
        self.assertEqual(
            identity,
            WebIdentity(
                user_id=42,
                telegram_id=5001,
                company_id="intertop",
                company_name="Intertop Retail",
                role="manager",
            ),
        )


class FakeTenantContextService:
    def __init__(self, context: Optional[TenantUserContext]) -> None:
        self._context = context
        self.calls: list[tuple[Path, int, str]] = []

    def resolve(
        self,
        db_path: Path,
        user_id: int,
        company_id: str,
    ) -> Optional[TenantUserContext]:
        self.calls.append((db_path, user_id, company_id))
        return self._context


class WebIdentityServiceDependencyTests(unittest.TestCase):
    def test_resolve_uses_tenant_context_after_user_lookup(self) -> None:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = Path(tmpdir.name) / "test.db"
        initialize_database(db_path)

        upsert_telegram_user(
            db_path,
            telegram_id=6001,
            username="user6001",
            first_name="Test",
            last_name="User",
        )
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (6001,),
            ).fetchone()
        assert row is not None
        user_id = int(row["id"])

        fake_tenant = FakeTenantContextService(
            TenantUserContext(
                user_id=user_id,
                company_id="intertop",
                company_name="Intertop Retail",
                role="admin",
            )
        )
        service = WebIdentityService(UserRepository(), fake_tenant)

        identity = service.resolve(db_path, 6001, "intertop")

        assert identity is not None
        self.assertEqual(len(fake_tenant.calls), 1)
        self.assertEqual(fake_tenant.calls[0], (db_path, user_id, "intertop"))
        self.assertEqual(identity.role, "admin")


if __name__ == "__main__":
    unittest.main()
