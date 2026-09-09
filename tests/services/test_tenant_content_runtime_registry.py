"""Tests for per-company filesystem runtime isolation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.tenant_content_runtime_registry import (
    TenantContentRuntimeRegistry,
)


def _write_course(base_dir: Path, slug: str, title: str) -> None:
    course_dir = base_dir / slug
    course_dir.mkdir(parents=True)
    (course_dir / "course.json").write_text(
        json.dumps({"slug": slug, "title": title, "status": "published"}),
        encoding="utf-8",
    )


class TenantContentRuntimeRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.courses_root = Path(self._tmpdir.name) / "courses"
        self.courses_root.mkdir()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_intertop_uses_legacy_courses_root(self) -> None:
        _write_course(self.courses_root, "legacy", "Legacy course")
        registry = TenantContentRuntimeRegistry(self.courses_root)

        runtime = registry.get_runtime("intertop")

        self.assertEqual(runtime.base_dir, self.courses_root.resolve())
        self.assertEqual([course.slug for course in runtime.get_courses()], ["legacy"])

    def test_new_company_uses_only_its_own_content_directory(self) -> None:
        _write_course(self.courses_root, "legacy", "Legacy course")
        _write_course(self.courses_root / "company-a", "alpha", "Alpha")
        _write_course(self.courses_root / "company-b", "beta", "Beta")
        registry = TenantContentRuntimeRegistry(self.courses_root)

        company_a = registry.get_runtime("company-a")
        company_b = registry.get_runtime("company-b")

        self.assertEqual([course.slug for course in company_a.get_courses()], ["alpha"])
        self.assertEqual([course.slug for course in company_b.get_courses()], ["beta"])
        self.assertIs(company_a, registry.get_runtime("company-a"))

    def test_invalid_company_id_cannot_escape_courses_root(self) -> None:
        registry = TenantContentRuntimeRegistry(self.courses_root)

        for invalid in ("", " ", "../other", "company/a", "company\\a", ".", ".."):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    registry.get_runtime(invalid)


if __name__ == "__main__":
    unittest.main()
