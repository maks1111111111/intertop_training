"""Database enforcement tests for per-company SaaS limits."""
from __future__ import annotations
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app.database.db import get_connection, initialize_database
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.company_usage_limit_repository import CompanyUsageLimitRepository

class CompanyUsageLimitsSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db_path = Path(self.tmp.name) / "test.db"; initialize_database(self.db_path)
        CompanyRepository().create(self.db_path, "company-a", "Company A")
        with get_connection(self.db_path) as c:
            self.first = int(c.execute("INSERT INTO users (username) VALUES ('one')").lastrowid)
            self.second = int(c.execute("INSERT INTO users (username) VALUES ('two')").lastrowid)
    def tearDown(self): self.tmp.cleanup()
    def test_member_and_course_limits_are_enforced(self):
        limits = CompanyUsageLimitRepository(); limits.set(self.db_path, "company-a", 1, 1)
        CompanyMembershipRepository().add(self.db_path, "company-a", self.first)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "member limit"):
            CompanyMembershipRepository().add(self.db_path, "company-a", self.second)
        with get_connection(self.db_path) as c:
            c.execute("INSERT INTO courses (company_id, slug, title) VALUES ('company-a', 'one', 'One')")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "course limit"):
                c.execute("INSERT INTO courses (company_id, slug, title) VALUES ('company-a', 'two', 'Two')")
    def test_null_limits_are_unlimited(self):
        CompanyUsageLimitRepository().set(self.db_path, "company-a", None, None)
        CompanyMembershipRepository().add(self.db_path, "company-a", self.first)
        CompanyMembershipRepository().add(self.db_path, "company-a", self.second)

if __name__ == "__main__": unittest.main()
