"""Tests for manual admin course creation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_manual_course_create_service import (
    AdminManualCourseCreateError,
    AdminManualCourseCreateRequest,
    AdminManualCourseCreateService,
)
from tests.web.test_web_ui import _create_test_app, _write_course


class AdminManualCourseCreateServiceTests(unittest.TestCase):
    """Unit tests for AdminManualCourseCreateService."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminManualCourseCreateService(self.courses_dir, self.runtime)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_course_writes_course_json(self) -> None:
        result = self.service.create_course(
            AdminManualCourseCreateRequest(
                title="Manual Course",
                description="Manual description",
                language="ru",
            )
        )

        course_json = json.loads(
            (self.courses_dir / result.slug / "course.json").read_text(encoding="utf-8")
        )
        self.assertEqual(course_json["title"], "Manual Course")
        self.assertEqual(course_json["description"], "Manual description")
        self.assertEqual(course_json["language"], "ru")
        self.assertEqual(course_json["slug"], result.slug)

    def test_create_course_empty_title_rejected(self) -> None:
        with self.assertRaises(AdminManualCourseCreateError) as ctx:
            self.service.create_course(
                AdminManualCourseCreateRequest(
                    title="   ",
                    description="",
                    language="ru",
                )
            )
        self.assertEqual(ctx.exception.message, "Название курса обязательно.")

    def test_create_course_invalid_language_rejected(self) -> None:
        with self.assertRaises(AdminManualCourseCreateError) as ctx:
            self.service.create_course(
                AdminManualCourseCreateRequest(
                    title="Valid title",
                    description="",
                    language="auto",
                )
            )
        self.assertEqual(ctx.exception.message, "Выберите поддерживаемый язык курса.")

    def test_create_course_refreshes_runtime(self) -> None:
        with patch(
            "app.web.admin_manual_course_create_service.RuntimeRefreshService"
        ) as refresh_cls:
            refresh = refresh_cls.return_value
            result = self.service.create_course(
                AdminManualCourseCreateRequest(
                    title="Visible Course",
                    description="",
                    language="en",
                )
            )
            refresh.refresh.assert_called_once()

        course = self.runtime.get_course(result.slug)
        self.assertIsNotNone(course)
        self.assertEqual(course.title, "Visible Course")

    def test_create_course_updates_preloaded_runtime_without_mock(self) -> None:
        self.runtime.get_courses()
        before_count = self.runtime.cached_courses_count()

        result = self.service.create_course(
            AdminManualCourseCreateRequest(
                title="Preloaded Course",
                description="",
                language="ru",
            )
        )

        self.assertEqual(self.runtime.cached_courses_count(), before_count + 1)
        course = self.runtime.get_course(result.slug)
        self.assertIsNotNone(course)
        self.assertEqual(course.title, "Preloaded Course")

    def test_write_failure_removes_partial_course_directory(self) -> None:
        with patch(
            "app.web.admin_manual_course_create_service._atomic_write_json",
            side_effect=OSError("write failed"),
        ):
            with self.assertRaises(AdminManualCourseCreateError):
                self.service.create_course(
                    AdminManualCourseCreateRequest(
                        title="Broken Course",
                        description="",
                        language="ru",
                    )
                )

        remaining = list(self.courses_dir.iterdir())
        self.assertEqual(remaining, [])

    def test_existing_course_directories_are_not_overwritten(self) -> None:
        _write_course(self.courses_dir, "existing-course", title="Existing")
        before = list(self.courses_dir.iterdir())

        result = self.service.create_course(
            AdminManualCourseCreateRequest(
                title="Another Course",
                description="",
                language="ru",
            )
        )

        self.assertNotEqual(result.slug, "existing-course")
        self.assertTrue((self.courses_dir / "existing-course" / "course.json").is_file())
        self.assertGreaterEqual(len(list(self.courses_dir.iterdir())), len(before) + 1)


class AdminManualCourseCreatePageTests(unittest.TestCase):
    """HTTP tests for manual course creation routes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_mode_page_returns_200(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создать с AI", response.text)
        self.assertIn("Создать вручную", response.text)
        self.assertIn('href="/admin/courses/new/ai"', response.text)
        self.assertIn('href="/admin/courses/new/manual"', response.text)

    def test_manual_page_returns_200(self) -> None:
        response = self.client.get("/admin/courses/new/manual")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса вручную", response.text)
        self.assertIn('name="title"', response.text)
        self.assertIn('name="description"', response.text)
        self.assertIn('name="language"', response.text)

    def test_manual_page_has_no_ai_fields(self) -> None:
        response = self.client.get("/admin/courses/new/manual")
        html = response.text
        self.assertNotIn('name="source_file"', html)
        self.assertNotIn('name="lesson_count"', html)
        self.assertNotIn('name="generate_quiz"', html)

    def test_manual_create_success_redirects_to_admin_detail(self) -> None:
        response = self.client.post(
            "/admin/courses/new/manual",
            data={
                "title": "Manual Web Course",
                "description": "Created manually",
                "language": "kk",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertRegex(response.headers["location"], r"^/admin/courses/course-[0-9a-f]{12}$")

        slug = response.headers["location"].rsplit("/", 1)[-1]
        course_json = json.loads(
            (self.courses_dir / slug / "course.json").read_text(encoding="utf-8")
        )
        self.assertEqual(course_json["title"], "Manual Web Course")
        self.assertEqual(course_json["description"], "Created manually")
        self.assertEqual(course_json["language"], "kk")

    def test_manual_create_empty_title_rejected(self) -> None:
        response = self.client.post(
            "/admin/courses/new/manual",
            data={"title": "   ", "description": "Keep me", "language": "ru"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Название курса обязательно.", response.text)
        self.assertIn("Keep me", response.text)

    def test_manual_create_invalid_language_rejected(self) -> None:
        response = self.client.post(
            "/admin/courses/new/manual",
            data={"title": "Valid", "description": "", "language": "auto"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите поддерживаемый язык курса.", response.text)

    def test_ai_wizard_moved_to_new_ai_route(self) -> None:
        response = self.client.get("/admin/courses/new/ai")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса", response.text)
        self.assertIn('action="/admin/courses/new/ai"', response.text)


if __name__ == "__main__":
    unittest.main()
