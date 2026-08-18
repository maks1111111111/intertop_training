"""Tests for password-based Web login and logout routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database.db import get_connection
from app.repositories.company_membership_repository import (
    CompanyMembershipRepository,
)
from app.repositories.company_repository import CompanyRepository
from app.repositories.password_credential_repository import (
    PasswordCredentialRepository,
)
from app.web.password_hashing_service import PasswordHashingService
from app.web.router import get_web_session_service
from app.web.web_session_config import WEB_SESSION_COOKIE_NAME
from app.web.web_session_service import WebSessionService
from tests.web.test_web_ui import _create_test_app


_TEST_SESSION_SECRET = (
    "test-web-session-secret-that-is-at-least-32-bytes"
)


class WebLoginRouteTests(unittest.TestCase):
    """Verify HTTP login creates and clears signed Web sessions."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()

        (
            self.app,
            self.db_tmp,
            self.db_path,
            self.upload_tmp,
        ) = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )

        self.session_service = WebSessionService(
            _TEST_SESSION_SECRET
        )
        self.app.state.web_session_service = self.session_service
        self.app.dependency_overrides[get_web_session_service] = (
            lambda: self.session_service
        )

        self.company_repository = CompanyRepository()
        self.membership_repository = CompanyMembershipRepository()
        self.credential_repository = PasswordCredentialRepository()
        self.password_hashing_service = PasswordHashingService()

        self.company_repository.create(
            self.db_path,
            company_id="login-company",
            name="Login Company",
        )

        self.user_id = self._create_password_user()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _create_password_user(self) -> int:
        with get_connection(self.db_path) as connection:
            user_id = int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name,
                        is_active
                    )
                    VALUES (NULL, ?, ?, ?, 1)
                    """,
                    (
                        "login-user",
                        "Login",
                        "User",
                    ),
                ).lastrowid
            )

        self.membership_repository.add(
            self.db_path,
            company_id="login-company",
            user_id=user_id,
            role="student",
        )

        password_hash = self.password_hashing_service.hash_password(
            "Strong-password-123!"
        )
        self.credential_repository.create(
            self.db_path,
            user_id=user_id,
            email="user@example.com",
            password_hash=password_hash,
        )

        return user_id

    def _valid_login_data(self) -> dict[str, str]:
        return {
            "email": "user@example.com",
            "password": "Strong-password-123!",
            "company_id": "login-company",
        }

    def test_login_page_returns_200(self) -> None:
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Вход в аккаунт", response.text)
        self.assertIn('name="email"', response.text)
        self.assertIn('name="password"', response.text)
        self.assertIn('name="company_id"', response.text)

    def test_valid_credentials_create_signed_session(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": " USER@example.com ",
                "password": "Strong-password-123!",
                "company_id": "login-company",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/dashboard",
        )

        token = response.cookies.get(WEB_SESSION_COOKIE_NAME)
        self.assertIsNotNone(token)
        assert token is not None

        session = self.session_service.resolve_token(token)

        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.user_id, self.user_id)
        self.assertEqual(
            session.company_id,
            "login-company",
        )

    def test_session_cookie_is_httponly_and_samesite_lax(self) -> None:
        response = self.client.post(
            "/login",
            data=self._valid_login_data(),
            follow_redirects=False,
        )

        cookie = response.headers.get("set-cookie", "").lower()

        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("path=/", cookie)

    def test_http_login_cookie_is_not_secure_in_local_test_client(
        self,
    ) -> None:
        response = self.client.post(
            "/login",
            data=self._valid_login_data(),
            follow_redirects=False,
        )

        cookie = response.headers.get("set-cookie", "").lower()

        self.assertNotIn("; secure", cookie)

    def test_wrong_password_returns_generic_error_without_cookie(
        self,
    ) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": "user@example.com",
                "password": "wrong-password",
                "company_id": "login-company",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Неверные данные для входа.",
            response.text,
        )
        self.assertNotIn(
            WEB_SESSION_COOKIE_NAME,
            response.cookies,
        )

    def test_unknown_email_returns_same_generic_error(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": "missing@example.com",
                "password": "Strong-password-123!",
                "company_id": "login-company",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Неверные данные для входа.",
            response.text,
        )

    def test_wrong_company_returns_same_generic_error(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": "user@example.com",
                "password": "Strong-password-123!",
                "company_id": "wrong-company",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Неверные данные для входа.",
            response.text,
        )

    def test_login_preserves_email_and_company_after_error(
        self,
    ) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": "user@example.com",
                "password": "wrong-password",
                "company_id": "login-company",
            },
        )

        self.assertIn(
            'value="user@example.com"',
            response.text,
        )
        self.assertIn(
            'value="login-company"',
            response.text,
        )
        self.assertNotIn(
            'value="wrong-password"',
            response.text,
        )

    def test_authenticated_user_is_redirected_away_from_login(
        self,
    ) -> None:
        token = self.session_service.create_token(
            user_id=self.user_id,
            company_id="login-company",
        )
        self.client.cookies.set(
            WEB_SESSION_COOKIE_NAME,
            token,
        )

        response = self.client.get(
            "/login",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["location"],
            "/dashboard",
        )

    def test_logout_clears_session_cookie(self) -> None:
        token = self.session_service.create_token(
            user_id=self.user_id,
            company_id="login-company",
        )
        self.client.cookies.set(
            WEB_SESSION_COOKIE_NAME,
            token,
        )

        response = self.client.post(
            "/logout",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/login",
        )

        cookie = response.headers.get("set-cookie", "").lower()

        self.assertIn(
            WEB_SESSION_COOKIE_NAME,
            cookie,
        )
        self.assertIn("max-age=0", cookie)

    def test_logout_does_not_require_existing_session(self) -> None:
        response = self.client.post(
            "/logout",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/login",
        )


if __name__ == "__main__":
    unittest.main()
