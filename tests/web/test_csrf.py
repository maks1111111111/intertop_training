"""Tests for browser-level CSRF protection."""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.csrf import SameOriginCSRFMiddleware


class SameOriginCSRFMiddlewareTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.add_middleware(SameOriginCSRFMiddleware)

        @app.get("/form")
        def form_page() -> dict[str, bool]:
            return {"ok": True}

        @app.post("/submit")
        def submit() -> dict[str, bool]:
            return {"ok": True}

        @app.post("/api/v1/write")
        def api_write() -> dict[str, bool]:
            return {"ok": True}

        self.client = TestClient(app, base_url="https://training.example")

    def test_cross_site_browser_post_is_rejected(self) -> None:
        response = self.client.post(
            "/submit",
            headers={
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_same_origin_browser_post_is_allowed(self) -> None:
        response = self.client.post(
            "/submit",
            headers={
                "Origin": "https://training.example",
                "Sec-Fetch-Site": "same-origin",
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_mismatched_origin_is_rejected_without_fetch_metadata(self) -> None:
        response = self.client.post(
            "/submit",
            headers={"Origin": "https://attacker.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_cross_origin_referer_is_rejected_when_origin_is_missing(self) -> None:
        response = self.client.post(
            "/submit",
            headers={"Referer": "https://attacker.example/form"},
        )

        self.assertEqual(response.status_code, 403)

    def test_non_browser_post_without_fetch_metadata_is_allowed(self) -> None:
        response = self.client.post("/submit")

        self.assertEqual(response.status_code, 200)

    def test_same_site_post_without_origin_is_rejected(self) -> None:
        response = self.client.post(
            "/submit",
            headers={"Sec-Fetch-Site": "same-site"},
        )

        self.assertEqual(response.status_code, 403)

    def test_safe_request_is_not_rejected(self) -> None:
        response = self.client.get(
            "/form",
            headers={
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_cross_site_api_write_is_also_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/write",
            headers={
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
