"""End-to-end tenant isolation through signed Web sessions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import get_connection, upsert_telegram_user
from app.repositories.company_membership_repository import CompanyMembershipRepository
from app.repositories.company_repository import CompanyRepository
from app.services.course_sync import sync_courses
from app.services.tenant_content_runtime_registry import (
    TenantContentRuntimeRegistry,
)
from app.web.web_session_config import WEB_SESSION_COOKIE_NAME
from app.web.web_session_service import WebSessionService
from tests.web.test_web_ui import _create_test_app, _write_course


_SESSION_SECRET = "e2e-web-session-secret-with-at-least-32-bytes"


class WebMultiCompanySessionE2ETests(unittest.TestCase):
    """Verify one signed user gets a complete, isolated tenant context."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.courses_root = Path(self._tmpdir.name) / "courses"
        self.courses_root.mkdir()
        (self.courses_root / "company-a").mkdir()
        (self.courses_root / "company-b").mkdir()
        _write_course(
            self.courses_root / "company-a",
            "alpha",
            title="Alpha A",
        )
        _write_course(
            self.courses_root / "company-b",
            "beta",
            title="Beta B",
        )

        self.app, self._db_tmp, self.db_path, self._upload_tmp = _create_test_app(
            self.courses_root,
            management_identity=False,
        )
        registry = TenantContentRuntimeRegistry(self.courses_root)
        self.app.state.content_runtime = registry.legacy_runtime
        self.app.state.tenant_content_runtimes = registry
        self.session_service = WebSessionService(_SESSION_SECRET)
        self.app.state.web_session_service = self.session_service
        self.client = TestClient(self.app)

        companies = CompanyRepository()
        self.memberships = CompanyMembershipRepository()
        companies.create(self.db_path, "company-a", "Company A")
        companies.create(self.db_path, "company-b", "Company B")

        self.shared_user_id = self._create_user(101, "shared-user", "Shared")
        self.company_a_user_id = self._create_user(102, "a-learner", "A Learner")
        self.company_b_user_id = self._create_user(103, "b-learner", "B Learner")

        self.memberships.add(
            self.db_path,
            "company-a",
            self.shared_user_id,
            role="student",
        )
        self.memberships.add(
            self.db_path,
            "company-a",
            self.company_a_user_id,
            role="student",
        )
        self.memberships.add(
            self.db_path,
            "company-b",
            self.shared_user_id,
            role="manager",
        )
        self.memberships.add(
            self.db_path,
            "company-b",
            self.company_b_user_id,
            role="student",
        )

        sync_courses(
            self.courses_root / "company-a",
            self.db_path,
            company_id="company-a",
        )
        sync_courses(
            self.courses_root / "company-b",
            self.db_path,
            company_id="company-b",
        )

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self._upload_tmp.cleanup()
        self._db_tmp.cleanup()
        self._tmpdir.cleanup()

    def _create_user(self, telegram_id: int, username: str, first_name: str) -> int:
        upsert_telegram_user(
            self.db_path,
            telegram_id,
            username,
            first_name,
            "Learner",
        )
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        assert row is not None
        return int(row["id"])

    def _headers_for_company(self, company_id: str) -> dict[str, str]:
        token = self.session_service.create_token(
            user_id=self.shared_user_id,
            company_id=company_id,
        )
        return {"Cookie": f"{WEB_SESSION_COOKIE_NAME}={token}"}

    def test_signed_session_switches_all_web_and_api_tenant_context(self) -> None:
        company_a_headers = self._headers_for_company("company-a")
        dashboard_a = self.client.get("/dashboard", headers=company_a_headers)
        catalog_a = self.client.get("/api/v1/courses", headers=company_a_headers)
        manager_a = self.client.get("/manager/team", headers=company_a_headers)

        self.assertEqual(dashboard_a.status_code, 200)
        self.assertIn("Alpha A", dashboard_a.text)
        self.assertNotIn("Beta B", dashboard_a.text)
        self.assertEqual(catalog_a.status_code, 200)
        self.assertEqual(
            [item["title"] for item in catalog_a.json()["items"]],
            ["Alpha A"],
        )
        self.assertEqual(manager_a.status_code, 403)

        company_b_headers = self._headers_for_company("company-b")
        dashboard_b = self.client.get("/dashboard", headers=company_b_headers)
        catalog_b = self.client.get("/api/v1/courses", headers=company_b_headers)
        manager_b = self.client.get("/manager/team", headers=company_b_headers)
        company_a_profile = self.client.get(
            f"/manager/team/{self.company_a_user_id}",
            headers=company_b_headers,
        )
        company_b_profile = self.client.get(
            f"/manager/team/{self.company_b_user_id}",
            headers=company_b_headers,
        )

        self.assertEqual(dashboard_b.status_code, 200)
        self.assertIn("Beta B", dashboard_b.text)
        self.assertNotIn("Alpha A", dashboard_b.text)
        self.assertEqual(catalog_b.status_code, 200)
        self.assertEqual(
            [item["title"] for item in catalog_b.json()["items"]],
            ["Beta B"],
        )
        self.assertEqual(manager_b.status_code, 200)
        self.assertIn("B Learner", manager_b.text)
        self.assertNotIn("A Learner", manager_b.text)
        self.assertEqual(company_a_profile.status_code, 404)
        self.assertEqual(company_b_profile.status_code, 200)

    def test_deactivated_membership_invalidates_existing_signed_session(self) -> None:
        headers = self._headers_for_company("company-a")

        self.assertEqual(
            self.client.get("/dashboard", headers=headers).status_code,
            200,
        )
        self.assertTrue(
            self.memberships.set_active(
                self.db_path,
                "company-a",
                self.shared_user_id,
                False,
            )
        )

        dashboard = self.client.get(
            "/dashboard",
            headers=headers,
            follow_redirects=False,
        )
        catalog = self.client.get("/api/v1/courses", headers=headers)
        manager = self.client.get(
            "/manager/team",
            headers=headers,
            follow_redirects=False,
        )

        self.assertEqual(dashboard.status_code, 303)
        self.assertEqual(dashboard.headers["location"], "/login")
        self.assertEqual(catalog.status_code, 401)
        self.assertEqual(manager.status_code, 303)
        self.assertEqual(manager.headers["location"], "/login")


if __name__ == "__main__":
    unittest.main()
