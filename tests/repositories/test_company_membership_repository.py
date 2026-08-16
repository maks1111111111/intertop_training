"""Tests for company_membership_repository."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import (
    get_connection,
    initialize_database,
    upsert_telegram_user,
)
from app.repositories.company_membership_repository import (
    CompanyMembership,
    CompanyMembershipRepository,
)
from app.repositories.company_repository import CompanyRepository


class CompanyMembershipRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.company_repository = CompanyRepository()
        self.repository = CompanyMembershipRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_company(self, company_id: str = "company-a", name: str = "Company A") -> None:
        self.company_repository.create(self.db_path, company_id=company_id, name=name)

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

    def test_add_and_get(self) -> None:
        self._create_company()
        user_id = self._create_user()

        created = self.repository.add(
            self.db_path,
            company_id="company-a",
            user_id=user_id,
        )

        self.assertIsInstance(created, CompanyMembership)
        self.assertEqual(created.company_id, "company-a")
        self.assertEqual(created.user_id, user_id)
        self.assertEqual(created.role, "student")
        self.assertTrue(created.is_active)

        loaded = self.repository.get(self.db_path, "company-a", user_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.id, created.id)

    def test_default_student_role(self) -> None:
        self._create_company()
        user_id = self._create_user()

        membership = self.repository.add(
            self.db_path,
            company_id="company-a",
            user_id=user_id,
        )

        self.assertEqual(membership.role, "student")

    def test_student_manager_admin_accepted(self) -> None:
        self._create_company()
        student_id = self._create_user(1001)
        manager_id = self._create_user(1002)
        admin_id = self._create_user(1003)

        student = self.repository.add(
            self.db_path,
            company_id="company-a",
            user_id=student_id,
            role="student",
        )
        manager = self.repository.add(
            self.db_path,
            company_id="company-a",
            user_id=manager_id,
            role="manager",
        )
        admin = self.repository.add(
            self.db_path,
            company_id="company-a",
            user_id=admin_id,
            role="admin",
        )

        self.assertEqual(student.role, "student")
        self.assertEqual(manager.role, "manager")
        self.assertEqual(admin.role, "admin")

    def test_invalid_role_rejected(self) -> None:
        self._create_company()
        user_id = self._create_user()

        with self.assertRaises(ValueError):
            self.repository.add(
                self.db_path,
                company_id="company-a",
                user_id=user_id,
                role="owner",
            )

    def test_empty_company_id_rejected(self) -> None:
        user_id = self._create_user()

        with self.assertRaises(ValueError):
            self.repository.add(
                self.db_path,
                company_id="  ",
                user_id=user_id,
            )

    def test_zero_user_id_rejected(self) -> None:
        self._create_company()

        with self.assertRaises(ValueError):
            self.repository.add(
                self.db_path,
                company_id="company-a",
                user_id=0,
            )

    def test_negative_user_id_rejected(self) -> None:
        self._create_company()

        with self.assertRaises(ValueError):
            self.repository.add(
                self.db_path,
                company_id="company-a",
                user_id=-1,
            )

    def test_duplicate_membership_rejected(self) -> None:
        self._create_company()
        user_id = self._create_user()
        self.repository.add(
            self.db_path,
            company_id="company-a",
            user_id=user_id,
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.add(
                self.db_path,
                company_id="company-a",
                user_id=user_id,
            )

    def test_unknown_get_returns_none(self) -> None:
        self._create_company()
        user_id = self._create_user()

        self.assertIsNone(
            self.repository.get(self.db_path, "company-a", user_id)
        )

    def test_fk_error_for_unknown_company(self) -> None:
        user_id = self._create_user()

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.add(
                self.db_path,
                company_id="missing-company",
                user_id=user_id,
            )

    def test_fk_error_for_unknown_user(self) -> None:
        self._create_company()

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.add(
                self.db_path,
                company_id="company-a",
                user_id=9999,
            )

    def test_list_for_company(self) -> None:
        self._create_company()
        first_user = self._create_user(1001)
        second_user = self._create_user(1002)
        self.repository.add(self.db_path, "company-a", first_user)
        self.repository.add(self.db_path, "company-a", second_user, role="manager")

        memberships = self.repository.list_for_company(self.db_path, "company-a")

        self.assertEqual(len(memberships), 2)
        self.assertEqual(memberships[0].user_id, first_user)
        self.assertEqual(memberships[1].user_id, second_user)

    def test_list_for_user(self) -> None:
        self._create_company("company-a", "Company A")
        self._create_company("company-b", "Company B")
        user_id = self._create_user()
        self.repository.add(self.db_path, "company-a", user_id)
        self.repository.add(self.db_path, "company-b", user_id, role="manager")

        memberships = self.repository.list_for_user(self.db_path, user_id)

        self.assertEqual(len(memberships), 2)
        self.assertEqual(
            tuple(membership.company_id for membership in memberships),
            ("company-a", "company-b"),
        )

    def test_active_only_filtering(self) -> None:
        self._create_company()
        active_user = self._create_user(1001)
        inactive_user = self._create_user(1002)
        self.repository.add(self.db_path, "company-a", active_user)
        self.repository.add(self.db_path, "company-a", inactive_user)
        self.repository.set_active(self.db_path, "company-a", inactive_user, False)

        active_only = self.repository.list_for_company(
            self.db_path,
            "company-a",
            active_only=True,
        )
        all_memberships = self.repository.list_for_company(
            self.db_path,
            "company-a",
            active_only=False,
        )

        self.assertEqual(len(active_only), 1)
        self.assertEqual(active_only[0].user_id, active_user)
        self.assertEqual(len(all_memberships), 2)

    def test_deterministic_ordering(self) -> None:
        self._create_company()
        third = self._create_user(1003)
        first = self._create_user(1001)
        second = self._create_user(1002)
        self.repository.add(self.db_path, "company-a", third)
        self.repository.add(self.db_path, "company-a", first)
        self.repository.add(self.db_path, "company-a", second)

        memberships = self.repository.list_for_company(
            self.db_path,
            "company-a",
            active_only=False,
        )

        self.assertEqual(
            tuple(membership.user_id for membership in memberships),
            (third, first, second),
        )
        self.assertLess(memberships[0].id, memberships[1].id)
        self.assertLess(memberships[1].id, memberships[2].id)

    def test_set_role(self) -> None:
        self._create_company()
        user_id = self._create_user()
        self.repository.add(self.db_path, "company-a", user_id)

        self.assertTrue(
            self.repository.set_role(
                self.db_path,
                "company-a",
                user_id,
                "admin",
            )
        )

        loaded = self.repository.get(self.db_path, "company-a", user_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.role, "admin")

    def test_set_role_invalid_role(self) -> None:
        self._create_company()
        user_id = self._create_user()
        self.repository.add(self.db_path, "company-a", user_id)

        with self.assertRaises(ValueError):
            self.repository.set_role(
                self.db_path,
                "company-a",
                user_id,
                "superadmin",
            )

    def test_set_role_unknown_returns_false(self) -> None:
        self._create_company()
        user_id = self._create_user()

        self.assertFalse(
            self.repository.set_role(
                self.db_path,
                "company-a",
                user_id,
                "admin",
            )
        )

    def test_set_active(self) -> None:
        self._create_company()
        user_id = self._create_user()
        self.repository.add(self.db_path, "company-a", user_id)

        self.assertTrue(
            self.repository.set_active(
                self.db_path,
                "company-a",
                user_id,
                False,
            )
        )

        loaded = self.repository.get(self.db_path, "company-a", user_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertFalse(loaded.is_active)

    def test_set_active_unknown_returns_false(self) -> None:
        self._create_company()
        user_id = self._create_user()

        self.assertFalse(
            self.repository.set_active(
                self.db_path,
                "company-a",
                user_id,
                False,
            )
        )

    def test_bool_conversion_is_correct(self) -> None:
        self._create_company()
        user_id = self._create_user()
        created = self.repository.add(self.db_path, "company-a", user_id)
        self.assertIs(created.is_active, True)

        self.repository.set_active(self.db_path, "company-a", user_id, False)
        loaded = self.repository.get(self.db_path, "company-a", user_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIs(loaded.is_active, False)


if __name__ == "__main__":
    unittest.main()
