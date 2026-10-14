"""Regression coverage for public discovery and private-page indexing rules."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as element_tree
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app


_PUBLIC_URLS = {
    "https://mentorconnect.kz/",
    "https://mentorconnect.kz/privacy",
    "https://mentorconnect.kz/terms",
}


class PublicSeoTests(unittest.TestCase):
    """Verify public SEO pages never expose private application routes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        courses_dir = Path(self.tmp.name) / "courses"
        courses_dir.mkdir()
        (
            self.app,
            self.db_tmp,
            self.db_path,
            self.upload_tmp,
        ) = _create_test_app(courses_dir, management_identity=False)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _authenticate(self) -> None:
        identity = WebIdentity(
            user_id=1,
            telegram_id=1,
            company_id="intertop",
            company_name="Intertop Retail",
            role="student",
        )

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = identity
            return identity

        self.app.dependency_overrides[get_current_web_identity] = provide_identity

    def test_robots_txt_is_public_and_references_the_public_sitemap(self) -> None:
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["content-type"])
        self.assertIn("User-agent: *", response.text)
        self.assertIn("Allow: /", response.text)
        self.assertIn("Sitemap: https://mentorconnect.kz/sitemap.xml", response.text)
        self.assertNotIn("Disallow: /\n", response.text)
        for private_path in (
            "/login",
            "/mfa/",
            "/dashboard",
            "/courses",
            "/manager/",
            "/admin",
            "/platform-admin",
            "/knowledge/",
            "/account/",
            "/api/",
        ):
            self.assertIn(f"Disallow: {private_path}", response.text)

    def test_sitemap_contains_only_the_three_approved_public_urls(self) -> None:
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response.headers["content-type"])
        root = element_tree.fromstring(response.content)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = {
            location.text
            for location in root.findall("sitemap:url/sitemap:loc", namespace)
        }
        self.assertEqual(urls, _PUBLIC_URLS)
        self.assertEqual(len(urls), 3)
        for private_path in (
            "/login",
            "/mfa/",
            "/dashboard",
            "/courses",
            "/manager",
            "/admin",
            "/platform-admin",
            "/knowledge",
            "/account",
            "/api",
        ):
            self.assertFalse(any(private_path in url for url in urls))

    def test_public_pages_have_indexable_metadata_and_canonicals(self) -> None:
        landing = self.client.get("/")
        privacy = self.client.get("/privacy")
        terms = self.client.get("/terms")

        self.assertEqual(landing.status_code, 200)
        self.assertIn('<meta name="robots" content="index,follow">', landing.text)
        self.assertIn('<link rel="canonical" href="https://mentorconnect.kz/">', landing.text)
        self.assertIn('property="og:title"', landing.text)
        self.assertIn('name="twitter:card" content="summary"', landing.text)
        self.assertNotIn('noindex,nofollow', landing.text)

        self.assertEqual(privacy.status_code, 200)
        self.assertIn('<meta name="robots" content="index,follow">', privacy.text)
        self.assertIn('<link rel="canonical" href="https://mentorconnect.kz/privacy">', privacy.text)
        self.assertNotIn('noindex,nofollow', privacy.text)

        self.assertEqual(terms.status_code, 200)
        self.assertIn('<meta name="robots" content="index,follow">', terms.text)
        self.assertIn('<link rel="canonical" href="https://mentorconnect.kz/terms">', terms.text)
        self.assertNotIn('noindex,nofollow', terms.text)

    def test_private_shared_template_pages_are_noindex_without_changing_access(self) -> None:
        login = self.client.get("/login")
        platform_login = self.client.get("/platform-admin/login")
        dashboard = self.client.get("/dashboard", follow_redirects=False)

        self.assertEqual(login.status_code, 200)
        self.assertIn('<meta name="robots" content="noindex,nofollow">', login.text)
        self.assertEqual(platform_login.status_code, 200)
        self.assertIn('<meta name="robots" content="noindex,nofollow">', platform_login.text)
        self.assertEqual(dashboard.status_code, 303)
        self.assertEqual(dashboard.headers["location"], "/login")

        self._authenticate()
        courses = self.client.get("/courses")
        self.assertEqual(courses.status_code, 200)
        self.assertIn('<meta name="robots" content="noindex,nofollow">', courses.text)


if __name__ == "__main__":
    unittest.main()
