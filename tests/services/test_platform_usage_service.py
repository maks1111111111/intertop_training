"""Tests for aggregate platform utilization metrics."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.services.platform_usage_service import PlatformUsageService


class PlatformUsageServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.companies = CompanyRepository()
        self.companies.create(self.db_path, "company-a", "Company A")
        self.companies.create(self.db_path, "company-b", "Company B")
        self.companies.set_active(self.db_path, "company-b", False)
        with get_connection(self.db_path) as connection:
            user_id = int(connection.execute("INSERT INTO users (username) VALUES ('learner')").lastrowid)
            course_id = int(connection.execute("INSERT INTO courses (company_id, slug, title) VALUES ('company-a', 'alpha', 'Alpha')").lastrowid)
            connection.execute("INSERT INTO enrollments (company_id, user_id, course_id, status) VALUES ('company-a', ?, ?, 'assigned')", (user_id, course_id))
            connection.execute("INSERT INTO knowledge_documents (company_id, document_id, title, original_filename, source_type, status) VALUES ('company-a', 'doc-a', 'Manual', 'manual.pdf', 'pdf', 'active')")
        CompanyMembershipRepository().add(self.db_path, "company-a", user_id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_returns_per_company_and_active_platform_totals(self) -> None:
        usage = PlatformUsageService().get_overview(self.db_path)

        self.assertEqual(usage.active_companies, 1)
        self.assertEqual(usage.active_members, 1)
        self.assertEqual(usage.courses, 1)
        self.assertEqual(usage.active_enrollments, 1)
        self.assertEqual(usage.active_documents, 1)
        self.assertEqual([company.company_id for company in usage.companies], ["company-a", "company-b"])
        self.assertFalse(usage.companies[1].is_active)


if __name__ == "__main__":
    unittest.main()
