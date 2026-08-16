"""Tests for tenant_context_service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.services.tenant_context_service import (
    TenantContextService,
    TenantUserContext,
)


class TenantContextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.company_repository = CompanyRepository()
        self.membership_repository = CompanyMembershipRepository()
        self.service = TenantContextService(
            self.company_repository,
            self.membership_repository,
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

    def _create_user(self, telegram_id: int = 1001) -> int:
        upsert_telegram_user(
            self.db_path,
            telegram_id=telegram_id,
            username=f"user{telegram_id}",
            first_name="Test",
            last_name="User",
        )
        with get_connection(self.db_path) as connection:
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

    # resolve

    def test_resolve_active_company_and_membership(self) -> None:
        self._create_company("intertop", "Intertop Retail")
        user_id = self._create_user()
        self._add_membership("intertop", user_id, role="manager")

        context = self.service.resolve(self.db_path, user_id, "intertop")

        self.assertIsInstance(context, TenantUserContext)
        assert context is not None
        self.assertEqual(context.user_id, user_id)
        self.assertEqual(context.company_id, "intertop")
        self.assertEqual(context.company_name, "Intertop Retail")
        self.assertEqual(context.role, "manager")

    def test_resolve_strips_company_id(self) -> None:
        self._create_company("intertop", "Intertop")
        user_id = self._create_user()
        self._add_membership("intertop", user_id)

        context = self.service.resolve(self.db_path, user_id, "  intertop  ")

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.company_id, "intertop")

    def test_resolve_missing_company_returns_none(self) -> None:
        user_id = self._create_user()

        self.assertIsNone(
            self.service.resolve(self.db_path, user_id, "missing-company")
        )

    def test_resolve_inactive_company_returns_none(self) -> None:
        self._create_company("inactive-co", "Inactive", active=False)
        user_id = self._create_user()
        self._add_membership("inactive-co", user_id)

        self.assertIsNone(
            self.service.resolve(self.db_path, user_id, "inactive-co")
        )

    def test_resolve_missing_membership_returns_none(self) -> None:
        self._create_company("intertop", "Intertop")
        user_id = self._create_user()

        self.assertIsNone(
            self.service.resolve(self.db_path, user_id, "intertop")
        )

    def test_resolve_inactive_membership_returns_none(self) -> None:
        self._create_company("intertop", "Intertop")
        user_id = self._create_user()
        self._add_membership("intertop", user_id, active=False)

        self.assertIsNone(
            self.service.resolve(self.db_path, user_id, "intertop")
        )

    def test_resolve_student_role(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="student")

        context = self.service.resolve(self.db_path, user_id, "company-a")

        assert context is not None
        self.assertEqual(context.role, "student")

    def test_resolve_admin_role(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        context = self.service.resolve(self.db_path, user_id, "company-a")

        assert context is not None
        self.assertEqual(context.role, "admin")

    def test_resolve_zero_user_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, 0, "intertop")

    def test_resolve_negative_user_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, -1, "intertop")

    def test_resolve_bool_user_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, True, "intertop")

    def test_resolve_empty_company_id_rejected(self) -> None:
        user_id = self._create_user()

        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, user_id, "")

    def test_resolve_whitespace_company_id_rejected(self) -> None:
        user_id = self._create_user()

        with self.assertRaises(ValueError):
            self.service.resolve(self.db_path, user_id, "   ")

    # list_for_user

    def test_list_for_user_no_memberships(self) -> None:
        user_id = self._create_user()

        self.assertEqual(self.service.list_for_user(self.db_path, user_id), ())

    def test_list_for_user_multiple_active_contexts(self) -> None:
        user_id = self._create_user()
        self._create_company("company-a", "Company A")
        self._create_company("company-b", "Company B")
        self._add_membership("company-a", user_id, role="student")
        self._add_membership("company-b", user_id, role="manager")

        contexts = self.service.list_for_user(self.db_path, user_id)

        self.assertEqual(len(contexts), 2)
        self.assertEqual(contexts[0].company_id, "company-a")
        self.assertEqual(contexts[0].role, "student")
        self.assertEqual(contexts[1].company_id, "company-b")
        self.assertEqual(contexts[1].role, "manager")

    def test_list_for_user_preserves_membership_order(self) -> None:
        user_id = self._create_user()
        self._create_company("company-z", "Z")
        self._create_company("company-a", "A")
        self._create_company("company-m", "M")
        self._add_membership("company-z", user_id)
        self._add_membership("company-a", user_id)
        self._add_membership("company-m", user_id)

        contexts = self.service.list_for_user(self.db_path, user_id)

        self.assertEqual(
            [context.company_id for context in contexts],
            ["company-z", "company-a", "company-m"],
        )

    def test_list_for_user_excludes_inactive_memberships(self) -> None:
        user_id = self._create_user()
        self._create_company("active-co", "Active")
        self._create_company("inactive-member-co", "Inactive Member")
        self._add_membership("active-co", user_id)
        self._add_membership("inactive-member-co", user_id, active=False)

        contexts = self.service.list_for_user(self.db_path, user_id)

        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].company_id, "active-co")

    def test_list_for_user_excludes_inactive_companies(self) -> None:
        user_id = self._create_user()
        self._create_company("active-co", "Active")
        self._create_company("inactive-co", "Inactive", active=False)
        self._add_membership("active-co", user_id)
        self._add_membership("inactive-co", user_id)

        contexts = self.service.list_for_user(self.db_path, user_id)

        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].company_id, "active-co")

    def test_list_for_user_multiple_companies_same_user(self) -> None:
        user_id = self._create_user()
        self._create_company("company-a", "Company A")
        self._create_company("company-b", "Company B")
        self._add_membership("company-a", user_id, role="student")
        self._add_membership("company-b", user_id, role="admin")

        contexts = self.service.list_for_user(self.db_path, user_id)

        self.assertEqual(len(contexts), 2)
        roles = {context.company_id: context.role for context in contexts}
        self.assertEqual(roles["company-a"], "student")
        self.assertEqual(roles["company-b"], "admin")

    # has_role

    def test_has_role_matching_student(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="student")

        self.assertTrue(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("student",),
            )
        )

    def test_has_role_matching_manager(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="manager")

        self.assertTrue(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("manager",),
            )
        )

    def test_has_role_matching_admin(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        self.assertTrue(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("admin",),
            )
        )

    def test_has_role_multiple_allowed_roles(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="manager")

        self.assertTrue(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("student", "manager", "admin"),
            )
        )

    def test_has_role_mismatch_returns_false(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="student")

        self.assertFalse(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("manager", "admin"),
            )
        )

    def test_has_role_inactive_membership_returns_false(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin", active=False)

        self.assertFalse(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("admin",),
            )
        )

    def test_has_role_inactive_company_returns_false(self) -> None:
        self._create_company("company-a", "Company A", active=False)
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        self.assertFalse(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("admin",),
            )
        )

    def test_has_role_empty_allowed_roles_returns_false(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        self.assertFalse(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                (),
            )
        )

    def test_has_role_unsupported_allowed_role_raises(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        with self.assertRaises(ValueError):
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("superadmin",),
            )

    def test_has_role_normalizes_allowed_roles(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="manager")

        self.assertTrue(
            self.service.has_role(
                self.db_path,
                user_id,
                "company-a",
                ("  Manager  ",),
            )
        )

    # can_manage_learning

    def test_can_manage_learning_student_false(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="student")

        self.assertFalse(
            self.service.can_manage_learning(self.db_path, user_id, "company-a")
        )

    def test_can_manage_learning_manager_true(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="manager")

        self.assertTrue(
            self.service.can_manage_learning(self.db_path, user_id, "company-a")
        )

    def test_can_manage_learning_admin_true(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        self.assertTrue(
            self.service.can_manage_learning(self.db_path, user_id, "company-a")
        )

    def test_can_manage_learning_inactive_membership_false(self) -> None:
        self._create_company("company-a", "Company A")
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="manager", active=False)

        self.assertFalse(
            self.service.can_manage_learning(self.db_path, user_id, "company-a")
        )

    def test_can_manage_learning_inactive_company_false(self) -> None:
        self._create_company("company-a", "Company A", active=False)
        user_id = self._create_user()
        self._add_membership("company-a", user_id, role="admin")

        self.assertFalse(
            self.service.can_manage_learning(self.db_path, user_id, "company-a")
        )


if __name__ == "__main__":
    unittest.main()
