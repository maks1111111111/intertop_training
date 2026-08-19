"""Regression tests for login page layout and paste-normalization UX."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.router import get_current_web_identity, get_web_session_service
from app.web.web_identity_service import WebIdentity
from app.web.web_session_service import WebSessionService
from tests.web.test_web_ui import _create_test_app

_TEST_SESSION_SECRET = (
    "test-web-session-secret-that-is-at-least-32-bytes"
)

_CSS_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "css" / "app.css"
)
_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "web"
    / "static"
    / "js"
    / "input_paste_normalize.js"
)


class WebLoginPageStructureTests(unittest.TestCase):
    """Verify login page markup exposes a vertical auth card layout."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )
        self.session_service = WebSessionService(_TEST_SESSION_SECRET)
        self.app.state.web_session_service = self.session_service
        self.app.dependency_overrides[get_web_session_service] = (
            lambda: self.session_service
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_login_page_uses_vertical_auth_form_structure(self) -> None:
        response = self.client.get("/login")

        html = response.text
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="auth-page"', html)
        self.assertIn('class="auth-card"', html)
        self.assertIn('class="auth-form"', html)
        self.assertIn('class="auth-field"', html)
        self.assertIn("auth-submit", html)

    def test_login_error_uses_dedicated_alert_block(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": "missing@example.com",
                "password": "wrong-password",
                "company_id": "login-company",
            },
        )

        html = response.text
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            html,
            r'<div class="auth-error" role="alert">\s*Неверные данные для входа\.',
        )
        self.assertIn('class="auth-form"', html)

    def test_login_page_includes_paste_normalize_script(self) -> None:
        response = self.client.get("/login")

        self.assertIn(
            '/static/js/input_paste_normalize.js',
            response.text,
        )

    def test_login_identifier_fields_opt_into_paste_trim(self) -> None:
        response = self.client.get("/login")

        html = response.text
        self.assertIn('name="email"', html)
        self.assertIn('name="company_id"', html)
        self.assertRegex(
            html,
            r'name="email"[^>]*data-paste-trim="edges"',
        )
        self.assertRegex(
            html,
            r'name="company_id"[^>]*data-paste-trim="edges"',
        )
        self.assertNotRegex(
            html,
            r'name="password"[^>]*data-paste-trim="edges"',
        )


class WebLoginCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = _CSS_PATH.read_text(encoding="utf-8")

    def test_auth_form_uses_vertical_layout(self) -> None:
        self.assertRegex(
            self.css,
            r"\.auth-form\s*\{[^}]*flex-direction:\s*column",
            re.DOTALL,
        )

    def test_auth_error_is_visually_distinct(self) -> None:
        self.assertRegex(
            self.css,
            r"\.auth-error\s*\{[^}]*background:\s*#fef2f2",
            re.DOTALL,
        )

    def test_auth_submit_is_full_width(self) -> None:
        self.assertRegex(
            self.css,
            r"\.auth-submit\s*\{[^}]*width:\s*100%",
            re.DOTALL,
        )


class WebInputPasteNormalizeJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = _JS_PATH.read_text(encoding="utf-8")

    def test_helper_trims_only_edge_whitespace(self) -> None:
        self.assertIn("trimEdgeWhitespace", self.script)
        self.assertIn("EDGE_WHITESPACE", self.script)
        self.assertIn("\\u00A0", self.script)

    def test_helper_respects_data_paste_trim_attribute(self) -> None:
        self.assertIn('dataset.pasteTrim !== "edges"', self.script)


if __name__ == "__main__":
    unittest.main()
