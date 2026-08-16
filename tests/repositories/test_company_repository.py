"""Tests for company_repository."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.company_repository import Company, CompanyRepository


class CompanyRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = CompanyRepository()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_create_and_get(self) -> None:
        created = self.repository.create(
            self.db_path,
            company_id="intertop",
            name="Intertop",
        )

        self.assertIsInstance(created, Company)
        self.assertEqual(created.id, "intertop")
        self.assertEqual(created.name, "Intertop")
        self.assertTrue(created.is_active)
        self.assertTrue(created.created_at)
        self.assertTrue(created.updated_at)

        loaded = self.repository.get_by_id(self.db_path, "intertop")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.id, created.id)
        self.assertEqual(loaded.name, created.name)

    def test_whitespace_normalization(self) -> None:
        created = self.repository.create(
            self.db_path,
            company_id="  intertop  ",
            name="  Intertop Retail  ",
        )

        self.assertEqual(created.id, "intertop")
        self.assertEqual(created.name, "Intertop Retail")

        loaded = self.repository.get_by_id(self.db_path, "intertop")
        self.assertIsNotNone(loaded)

    def test_empty_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.create(self.db_path, company_id="", name="Name")

    def test_empty_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.create(self.db_path, company_id="company-a", name="   ")

    def test_duplicate_id_rejected(self) -> None:
        self.repository.create(self.db_path, company_id="company-a", name="First")

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create(self.db_path, company_id="company-a", name="Second")

    def test_unknown_id_returns_none(self) -> None:
        self.assertIsNone(
            self.repository.get_by_id(self.db_path, "missing-company")
        )

    def test_list_active_excludes_inactive_companies(self) -> None:
        self.repository.create(self.db_path, company_id="active-a", name="Active A")
        self.repository.create(self.db_path, company_id="active-b", name="Active B")
        self.repository.create(self.db_path, company_id="inactive-c", name="Inactive C")
        self.repository.set_active(self.db_path, "inactive-c", False)

        active = self.repository.list_active(self.db_path)

        self.assertEqual(tuple(company.id for company in active), ("active-a", "active-b"))

    def test_list_active_deterministic_ordering(self) -> None:
        self.repository.create(self.db_path, company_id="company-z", name="Z")
        self.repository.create(self.db_path, company_id="company-a", name="A")
        self.repository.create(self.db_path, company_id="company-m", name="M")

        active = self.repository.list_active(self.db_path)

        self.assertEqual(
            tuple(company.id for company in active),
            ("company-a", "company-m", "company-z"),
        )

    def test_set_active_works(self) -> None:
        self.repository.create(self.db_path, company_id="company-a", name="Company A")

        self.assertTrue(
            self.repository.set_active(self.db_path, "company-a", False)
        )

        loaded = self.repository.get_by_id(self.db_path, "company-a")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertFalse(loaded.is_active)
        self.assertNotIn("company-a", tuple(c.id for c in self.repository.list_active(self.db_path)))

    def test_set_active_unknown_returns_false(self) -> None:
        self.assertFalse(
            self.repository.set_active(self.db_path, "missing-company", False)
        )

    def test_set_active_refreshes_updated_at(self) -> None:
        self.repository.create(
            self.db_path,
            company_id="company-a",
            name="Company A",
        )

        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                UPDATE companies
                SET updated_at = '2000-01-01 00:00:00'
                WHERE id = ?
                """,
                ("company-a",),
            )

        self.assertTrue(
            self.repository.set_active(self.db_path, "company-a", False)
        )

        loaded = self.repository.get_by_id(self.db_path, "company-a")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertNotEqual(loaded.updated_at, "2000-01-01 00:00:00")

    def test_bool_conversion_is_correct(self) -> None:
        created = self.repository.create(
            self.db_path,
            company_id="company-a",
            name="Company A",
        )
        self.assertIs(created.is_active, True)

        self.repository.set_active(self.db_path, "company-a", False)
        loaded = self.repository.get_by_id(self.db_path, "company-a")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIs(loaded.is_active, False)


if __name__ == "__main__":
    unittest.main()
