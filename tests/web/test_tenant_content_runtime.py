"""HTTP coverage for tenant-scoped Web course content."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.services.tenant_content_runtime_registry import (
    TenantContentRuntimeRegistry,
)
from app.web.router import get_current_web_identity, router
from app.web.web_identity_service import WebIdentity


def _write_course(base_dir: Path, slug: str, title: str) -> None:
    course_dir = base_dir / slug
    course_dir.mkdir(parents=True)
    (course_dir / "course.json").write_text(
        json.dumps({"slug": slug, "title": title, "status": "published"}),
        encoding="utf-8",
    )


class TenantContentRuntimeWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        courses_root = Path(self._tmpdir.name) / "courses"
        courses_root.mkdir()
        _write_course(courses_root, "legacy", "Legacy only")
        _write_course(courses_root / "company-a", "alpha", "Alpha only")
        _write_course(courses_root / "company-b", "beta", "Beta only")

        registry = TenantContentRuntimeRegistry(courses_root)
        self._identity = WebIdentity(
            user_id=1,
            telegram_id=None,
            company_id="company-a",
            company_name="Company A",
            role="student",
        )
        app = FastAPI()
        app.state.content_runtime = registry.legacy_runtime
        app.state.tenant_content_runtimes = registry
        app.include_router(router)

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = self._identity
            return self._identity

        app.dependency_overrides[get_current_web_identity] = provide_identity
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_course_catalog_uses_verified_session_company_runtime(self) -> None:
        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha only", response.text)
        self.assertNotIn("Beta only", response.text)
        self.assertNotIn("Legacy only", response.text)


if __name__ == "__main__":
    unittest.main()
