"""End-to-end access boundaries for the isolated platform-admin contour."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import get_connection
from app.repositories.password_credential_repository import PasswordCredentialRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.repositories.company_repository import CompanyRepository
from app.web.password_hashing_service import PasswordHashingService
from app.web.router import get_web_session_service
from app.web.web_session_service import (
    PLATFORM_SESSION_SCOPE,
    WebSessionService,
)
from app.web.web_session_config import PLATFORM_SESSION_COOKIE_NAME, WEB_SESSION_COOKIE_NAME
from tests.web.test_web_ui import _create_test_app


_SESSION_SECRET = "platform-route-session-secret-with-at-least-32-bytes"


class PlatformAdminRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        courses_dir = Path(self.tmp.name) / "courses"
        courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            courses_dir,
            management_identity=False,
        )
        self.session_service = WebSessionService(_SESSION_SECRET)
        self.app.state.web_session_service = self.session_service
        self.app.dependency_overrides[get_web_session_service] = (
            lambda: self.session_service
        )
        self.client = TestClient(self.app)
        self.owner_id = self._create_platform_owner()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _create_platform_owner(self) -> int:
        with get_connection(self.db_path) as connection:
            user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('platform-owner')"
                ).lastrowid
            )
        passwords = PasswordHashingService()
        PasswordCredentialRepository().create(
            self.db_path,
            user_id=user_id,
            email="owner@example.com",
            password_hash=passwords.hash_password("Strong-password-123!"),
        )
        PlatformAdminRepository().bootstrap_owner(self.db_path, user_id)
        return user_id

    def _login(self):
        return self.client.post(
            "/platform-admin/login",
            data={
                "email": "owner@example.com",
                "password": "Strong-password-123!",
            },
            follow_redirects=False,
        )

    def test_owner_can_log_in_without_tenant_company_or_membership(self) -> None:
        response = self._login()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/platform-admin")
        dashboard = self.client.get("/platform-admin")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Управление платформой", dashboard.text)
        self.assertIn("Владелец", dashboard.text)

    def test_audit_history_is_visible_to_owner_only(self) -> None:
        self._login()

        owner_response = self.client.get("/platform-admin/audit")
        self.assertEqual(owner_response.status_code, 200)
        self.assertIn("platform_admin.bootstrap_owner", owner_response.text)

        with get_connection(self.db_path) as connection:
            other_id = int(connection.execute("INSERT INTO users (username) VALUES ('other-admin')").lastrowid)
            connection.execute("INSERT INTO platform_admins (user_id) VALUES (?)", (other_id,))
        token = self.session_service.create_token(
            user_id=other_id,
            company_id="__platform_admin__",
            scope=PLATFORM_SESSION_SCOPE,
        )
        other_response = self.client.get(
            "/platform-admin/audit",
            headers={"Cookie": f"{PLATFORM_SESSION_COOKIE_NAME}={token}"},
        )
        self.assertEqual(other_response.status_code, 403)

    def test_usage_is_visible_to_owner_only(self) -> None:
        CompanyRepository().create(self.db_path, "usage-company", "Usage Co")
        self._login()

        owner_response = self.client.get("/platform-admin/usage")
        self.assertEqual(owner_response.status_code, 200)
        self.assertIn("Usage Co", owner_response.text)
        self.assertIn("Агрегированные показатели", owner_response.text)

        updated = self.client.post(
            "/platform-admin/usage/usage-company/limits",
            data={"max_active_members": "10", "max_courses": "2", "reason": "Plan change", "current_password": "Strong-password-123!"},
            follow_redirects=False,
        )
        self.assertEqual(updated.status_code, 303)
        refreshed = self.client.get("/platform-admin/usage")
        self.assertIn('value="10"', refreshed.text)
        self.assertIn('value="2"', refreshed.text)

    def test_usage_limit_error_is_rendered_inline(self) -> None:
        CompanyRepository().create(self.db_path, "usage-company", "Usage Co")
        self._login()

        response = self.client.post(
            "/platform-admin/usage/usage-company/limits",
            data={
                "max_active_members": "10",
                "max_courses": "2",
                "reason": "Plan change",
                "current_password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Не удалось подтвердить текущий пароль", response.text)
        self.assertIn("Компании и лимиты", response.text)

    def test_owner_navigation_exposes_only_owner_sections(self) -> None:
        self._login()

        response = self.client.get("/platform-admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Разделы Platform Admin", response.text)
        for path in (
            "/platform-admin/companies",
            "/platform-admin/usage",
            "/platform-admin/admins",
            "/platform-admin/audit",
        ):
            self.assertIn(path, response.text)

    def test_platform_session_is_not_accepted_by_tenant_routes(self) -> None:
        self._login()

        response = self.client.get("/dashboard", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_tenant_scoped_session_is_not_accepted_by_platform_routes(self) -> None:
        token = self.session_service.create_token(
            user_id=self.owner_id,
            company_id="some-tenant",
        )

        response = self.client.get(
            "/platform-admin",
            headers={"Cookie": f"{WEB_SESSION_COOKIE_NAME}={token}"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/platform-admin/login")

    def test_platform_session_is_revoked_when_owner_is_deactivated(self) -> None:
        self._login()
        with get_connection(self.db_path) as connection:
            connection.execute(
                "UPDATE users SET is_active = 0 WHERE id = ?",
                (self.owner_id,),
            )

        response = self.client.get("/platform-admin", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/platform-admin/login")

    def test_platform_cookie_contains_platform_scope(self) -> None:
        self._login()
        token = self.client.cookies.get(PLATFORM_SESSION_COOKIE_NAME)
        self.assertIsNotNone(token)
        assert token is not None
        session = self.session_service.resolve_token(token)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.scope, PLATFORM_SESSION_SCOPE)

    def test_platform_login_preserves_existing_tenant_session_cookie(self) -> None:
        tenant_token = self.session_service.create_token(
            user_id=self.owner_id,
            company_id="some-tenant",
        )
        self.client.cookies.set(WEB_SESSION_COOKIE_NAME, tenant_token)

        self._login()

        self.assertEqual(
            self.client.cookies.get(WEB_SESSION_COOKIE_NAME),
            tenant_token,
        )
        self.assertIsNotNone(
            self.client.cookies.get(PLATFORM_SESSION_COOKIE_NAME)
        )

    def test_owner_can_create_and_deactivate_company_with_audit_reason(self) -> None:
        self._login()

        created = self.client.post(
            "/platform-admin/companies",
            data={
                "company_id": "north-shop",
                "name": "North Shop",
                "reason": "Initial customer provisioning",
                "current_password": "Strong-password-123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(created.status_code, 303)
        disabled = self.client.post(
            "/platform-admin/companies/north-shop/status",
            data={
                "state": "inactive",
                "reason": "Contract ended",
                "current_password": "Strong-password-123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(disabled.status_code, 303)

        companies_page = self.client.get("/platform-admin/companies")
        self.assertEqual(companies_page.status_code, 200)
        self.assertIn("North Shop", companies_page.text)
        self.assertIn("Отключена", companies_page.text)
        events = PlatformAdminRepository().list_audit_events(self.db_path)
        self.assertEqual(events[0].action, "company.deactivated")
        self.assertEqual(events[0].reason, "Contract ended")

    def test_non_owner_platform_admin_cannot_mutate_companies(self) -> None:
        with get_connection(self.db_path) as connection:
            user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('read-only-admin')"
                ).lastrowid
            )
            connection.execute(
                "INSERT INTO platform_admins (user_id) VALUES (?)",
                (user_id,),
            )
        token = self.session_service.create_token(
            user_id=user_id,
            company_id="__platform_admin__",
            scope=PLATFORM_SESSION_SCOPE,
        )

        response = self.client.post(
            "/platform-admin/companies",
            headers={"Cookie": f"{PLATFORM_SESSION_COOKIE_NAME}={token}"},
            data={
                "company_id": "north-shop",
                "name": "North Shop",
                "reason": "Unauthorized test",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Platform owner required")

    def test_operator_cannot_read_global_company_or_admin_metadata(self) -> None:
        CompanyRepository().create(self.db_path, "secret-company", "Secret Co")
        with get_connection(self.db_path) as connection:
            operator_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('support-operator')"
                ).lastrowid
            )
            connection.execute(
                "INSERT INTO platform_admins (user_id) VALUES (?)",
                (operator_id,),
            )
        token = self.session_service.create_token(
            user_id=operator_id,
            company_id="__platform_admin__",
            scope=PLATFORM_SESSION_SCOPE,
        )
        headers = {"Cookie": f"{PLATFORM_SESSION_COOKIE_NAME}={token}"}

        dashboard = self.client.get("/platform-admin", headers=headers)
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotIn("Secret Co", dashboard.text)
        self.assertNotIn("secret-company", dashboard.text)
        self.assertNotIn("/platform-admin/companies", dashboard.text)
        self.assertNotIn("/platform-admin/admins", dashboard.text)

        for path in ("/platform-admin/companies", "/platform-admin/admins"):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"], "Platform owner required")

    def test_cross_site_request_cannot_create_company_with_owner_session(self) -> None:
        self._login()

        response = self.client.post(
            "/platform-admin/companies",
            headers={
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
            data={
                "company_id": "attacker-company",
                "name": "Attacker Company",
                "reason": "Cross-site request",
                "current_password": "Strong-password-123!",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.text, "Forbidden")
        self.assertIsNone(
            CompanyRepository().get_by_id(self.db_path, "attacker-company")
        )

    def test_owner_can_issue_read_only_support_and_open_diagnostics(self) -> None:
        CompanyRepository().create(self.db_path, "support-company", "Support Co")
        self._login()

        granted = self.client.post(
            "/platform-admin/support",
            data={
                "operator_user_id": str(self.owner_id),
                "company_id": "support-company",
                "duration_minutes": "15",
                "reason": "Investigate ticket INC-42",
                "current_password": "Strong-password-123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(granted.status_code, 303)
        support_page = self.client.get("/platform-admin/support")
        self.assertEqual(support_page.status_code, 200)
        self.assertIn("Support Co", support_page.text)
        self.assertIn("Открыть диагностику", support_page.text)

        diagnostics = self.client.get("/platform-admin/support/1")
        self.assertEqual(diagnostics.status_code, 200)
        self.assertIn("Персональные данные и изменения недоступны", diagnostics.text)
        self.assertIn("Активные сотрудники", diagnostics.text)

    def test_support_form_offers_only_active_companies(self) -> None:
        CompanyRepository().create(self.db_path, "active-company", "Active Co")
        CompanyRepository().create(self.db_path, "inactive-company", "Inactive Co")
        CompanyRepository().set_active(self.db_path, "inactive-company", False)
        self._login()

        support_page = self.client.get("/platform-admin/support")

        self.assertEqual(support_page.status_code, 200)
        self.assertIn("Active Co", support_page.text)
        self.assertNotIn("Inactive Co", support_page.text)
        self.assertNotIn('value="inactive-company"', support_page.text)

    def test_support_grant_requires_fresh_owner_password_confirmation(self) -> None:
        CompanyRepository().create(self.db_path, "support-company", "Support Co")
        self._login()

        response = self.client.post(
            "/platform-admin/support",
            data={
                "operator_user_id": str(self.owner_id),
                "company_id": "support-company",
                "duration_minutes": "15",
                "reason": "Investigate ticket INC-43",
                "current_password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Не удалось подтвердить текущий пароль", response.text)
        self.assertNotIn("INC-43", response.text)

    def test_deactivating_company_invalidates_existing_support_diagnostics(self) -> None:
        CompanyRepository().create(self.db_path, "support-company", "Support Co")
        self._login()
        granted = self.client.post(
            "/platform-admin/support",
            data={
                "operator_user_id": str(self.owner_id),
                "company_id": "support-company",
                "duration_minutes": "15",
                "reason": "Investigate ticket INC-44",
                "current_password": "Strong-password-123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(granted.status_code, 303)
        deactivated = self.client.post(
            "/platform-admin/companies/support-company/status",
            data={
                "state": "inactive",
                "reason": "Contract ended",
                "current_password": "Strong-password-123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(deactivated.status_code, 303)

        diagnostics = self.client.get("/platform-admin/support/1")

        self.assertEqual(diagnostics.status_code, 404)

    def test_operator_cannot_see_other_operators_support_metadata(self) -> None:
        CompanyRepository().create(self.db_path, "operator-company", "Operator Co")
        CompanyRepository().create(self.db_path, "other-company", "Other Co")
        with get_connection(self.db_path) as connection:
            operator_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('support-operator')"
                ).lastrowid
            )
            other_operator_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('other-operator')"
                ).lastrowid
            )
            connection.executemany(
                "INSERT INTO platform_admins (user_id) VALUES (?)",
                ((operator_id,), (other_operator_id,)),
            )
        self._login()
        for operator_id_value, company_id, reason in (
            (operator_id, "operator-company", "My support ticket"),
            (other_operator_id, "other-company", "Other support ticket"),
        ):
            granted = self.client.post(
                "/platform-admin/support",
                data={
                    "operator_user_id": str(operator_id_value),
                    "company_id": company_id,
                    "duration_minutes": "15",
                    "reason": reason,
                    "current_password": "Strong-password-123!",
                },
                follow_redirects=False,
            )
            self.assertEqual(granted.status_code, 303)

        token = self.session_service.create_token(
            user_id=operator_id,
            company_id="__platform_admin__",
            scope=PLATFORM_SESSION_SCOPE,
        )
        response = self.client.get(
            "/platform-admin/support",
            headers={"Cookie": f"{PLATFORM_SESSION_COOKIE_NAME}={token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("operator-company", response.text)
        self.assertIn("My support ticket", response.text)
        self.assertNotIn("other-company", response.text)
        self.assertNotIn("Other support ticket", response.text)
        self.assertNotIn("Пользователь #", response.text)

    def test_company_lifecycle_requires_fresh_owner_password_confirmation(self) -> None:
        self._login()

        response = self.client.post(
            "/platform-admin/companies",
            data={
                "company_id": "north-shop",
                "name": "North Shop",
                "reason": "Initial customer provisioning",
                "current_password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Не удалось подтвердить текущий пароль", response.text)
        self.assertIsNone(CompanyRepository().get_by_id(self.db_path, "north-shop"))


if __name__ == "__main__":
    unittest.main()
