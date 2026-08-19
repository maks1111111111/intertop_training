"""Regression tests for sticky authenticated sidebar layout."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app

_CSS_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "css" / "app.css"
)


class WebSidebarLayoutCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = _CSS_PATH.read_text(encoding="utf-8")

    def test_sidebar_uses_sticky_viewport_height_layout(self) -> None:
        self.assertRegex(
            self.css,
            r"\.sidebar\s*\{[^}]*position:\s*sticky",
            re.DOTALL,
        )
        self.assertRegex(
            self.css,
            r"\.sidebar\s*\{[^}]*height:\s*100vh",
            re.DOTALL,
        )

    def test_sidebar_navigation_scrolls_independently(self) -> None:
        self.assertRegex(
            self.css,
            r"\.sidebar-nav\s*\{[^}]*overflow-y:\s*auto",
            re.DOTALL,
        )
        self.assertRegex(
            self.css,
            r"\.sidebar-nav\s*\{[^}]*min-height:\s*0",
            re.DOTALL,
        )

    def test_sidebar_account_footer_does_not_shrink(self) -> None:
        self.assertRegex(
            self.css,
            r"\.sidebar-account\s*\{[^}]*flex-shrink:\s*0",
            re.DOTALL,
        )
        self.assertRegex(
            self.css,
            r"\.sidebar-account\s*\{[^}]*margin-top:\s*auto",
            re.DOTALL,
        )


class WebSidebarLayoutMarkupTests(unittest.TestCase):
    """Verify authenticated pages still expose sidebar account markup."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )
        self.client = TestClient(self.app)

        identity = WebIdentity(
            user_id=10,
            telegram_id=None,
            company_id="intertop",
            company_name="Intertop Retail",
            role="student",
        )

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = identity
            return identity

        self.app.dependency_overrides[get_current_web_identity] = provide_identity

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_authenticated_page_keeps_sidebar_account_block(self) -> None:
        response = self.client.get("/courses")

        html = response.text
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="sidebar-account"', html)
        self.assertIn('class="sidebar-nav"', html)
        self.assertIn('action="/logout"', html)


if __name__ == "__main__":
    unittest.main()
