"""Migration coverage for tenant-owned course catalog rows."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.migrations import (
    migrate_companies_table,
    migrate_courses_tenant_scope,
)


class CoursesTenantSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "legacy.db"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_legacy_courses_receive_intertop_owner_and_allow_same_slug_per_tenant(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    cover_path TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO courses (id, slug, title, status)
                VALUES (7, 'safety', 'Legacy Safety', 'published');
                """
            )
            migrate_companies_table(connection)
            migrate_courses_tenant_scope(connection)
            connection.execute(
                "INSERT INTO companies (id, name) VALUES ('company-a', 'Company A')"
            )
            connection.execute(
                """INSERT INTO courses (company_id, slug, title, status)
                   VALUES ('company-a', 'safety', 'Tenant Safety', 'published')"""
            )
            rows = connection.execute(
                "SELECT id, company_id, title FROM courses WHERE slug = 'safety' ORDER BY id"
            ).fetchall()

        self.assertEqual(
            [(row["id"], row["company_id"], row["title"]) for row in rows],
            [(7, "intertop", "Legacy Safety"), (8, "company-a", "Tenant Safety")],
        )


if __name__ == "__main__":
    unittest.main()
