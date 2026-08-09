"""Tests for the admin course generation review step."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from fastapi.testclient import TestClient

from app.web.admin_upload_service import AdminReviewError, AdminUploadService
from tests.web.test_admin_course_upload import _default_form_data
from tests.web.test_web_ui import _create_test_app, _write_course


def _extract_hidden_value(html: str, name: str) -> str:
    pattern = rf'name="{re.escape(name)}" value="([^"]*)"'
    match = re.search(pattern, html)
    if match is None:
        raise AssertionError(f"Hidden field {name!r} not found in HTML")
    return match.group(1)


class AdminCourseGenerationReviewTests(unittest.TestCase):
    """Verify the pre-generation review step after source upload."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.upload_dir = self.app.state.upload_dir
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _post_upload(
        self,
        filename: str = "source.pdf",
        content: bytes = b"%PDF-1.4 test",
        *,
        form_data: Optional[dict] = None,
    ):
        data = dict(_default_form_data())
        if form_data:
            data.update(form_data)
        files = {"source_file": (filename, content, "application/octet-stream")}
        return self.client.post("/admin/courses/new", data=data, files=files)

    def _upload_and_extract_state(self) -> tuple[str, dict[str, str]]:
        response = self._post_upload()
        self.assertEqual(response.status_code, 200)
        html = response.text
        review_data = {
            "upload_id": _extract_hidden_value(html, "upload_id"),
            "original_filename": _extract_hidden_value(html, "original_filename"),
            "course_title": _extract_hidden_value(html, "course_title"),
            "description": _extract_hidden_value(html, "description"),
            "source_language": _extract_hidden_value(html, "source_language"),
            "output_language": _extract_hidden_value(html, "output_language"),
            "lesson_count": _extract_hidden_value(html, "lesson_count"),
            "lesson_size": _extract_hidden_value(html, "lesson_size"),
            "difficulty": _extract_hidden_value(html, "difficulty"),
            "include_explanations": "1",
        }
        return html, review_data

    def test_confirm_page_has_functional_continue_form(self) -> None:
        response = self._post_upload()
        html = response.text

        self.assertIn('action="/admin/courses/new/review"', html)
        self.assertIn('method="post"', html)
        self.assertIn('name="upload_id"', html)
        self.assertIn('type="submit">Продолжить</button>', html)
        self.assertNotIn('href="#">Продолжить</a>', html)

    def test_review_page_renders_submitted_configuration(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        response = self.client.post("/admin/courses/new/review", data=review_data)

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Проверка перед созданием", html)
        self.assertIn("Материал готов к созданию курса", html)
        self.assertIn("source.pdf", html)
        self.assertIn("PDF", html)
        self.assertIn("Новый курс", html)
        self.assertIn("Русский", html)
        self.assertIn("Beginner", html)
        self.assertIn("Medium", html)
        self.assertIn("Include Explanations", html)
        self.assertIn("Создать курс", html)
        self.assertIn("На следующем шаге здесь будет запущено создание курса.", html)

    def test_review_resolves_upload_by_upload_id(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        stored_files = list(self.upload_dir.iterdir())
        self.assertEqual(len(stored_files), 1)
        stored_name = stored_files[0].name
        self.assertTrue(stored_name.startswith(review_data["upload_id"]))

        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Проверка перед созданием", response.text)

    def test_malformed_upload_id_is_rejected(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        review_data["upload_id"] = "../../etc/passwd"

        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса", response.text)
        self.assertIn("Недействительный идентификатор загрузки", response.text)

    def test_nonexistent_upload_id_is_rejected(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        review_data["upload_id"] = "a" * 32

        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса", response.text)
        self.assertIn("Загруженный файл не найден", response.text)

    def test_traversal_like_upload_id_cannot_escape_upload_dir(self) -> None:
        service = AdminUploadService(self.upload_dir)
        with self.assertRaises(AdminReviewError):
            service.resolve_upload("../" + ("a" * 28))

    def test_no_absolute_upload_path_in_confirm_or_review_html(self) -> None:
        confirm_response = self._post_upload()
        _confirm_html, review_data = self._upload_and_extract_state()

        upload_root = str(self.upload_dir.resolve())
        self.assertNotIn(upload_root, confirm_response.text)

        review_response = self.client.post(
            "/admin/courses/new/review",
            data=review_data,
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertNotIn(upload_root, review_response.text)

    def test_review_does_not_create_course_directory(self) -> None:
        before = list(self.courses_dir.iterdir())
        _confirm_html, review_data = self._upload_and_extract_state()
        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)
        after = list(self.courses_dir.iterdir())
        self.assertEqual(before, after)

    def test_review_does_not_change_existing_published_course(self) -> None:
        _write_course(self.courses_dir, "existing")
        existing_course_json = (
            self.courses_dir / "existing" / "course.json"
        ).read_text(encoding="utf-8")
        course_dirs_before = {
            path.name for path in self.courses_dir.iterdir() if path.is_dir()
        }

        _confirm_html, review_data = self._upload_and_extract_state()
        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)

        course_dirs_after = {
            path.name for path in self.courses_dir.iterdir() if path.is_dir()
        }
        self.assertEqual(course_dirs_before, course_dirs_after)
        self.assertEqual(
            (self.courses_dir / "existing" / "course.json").read_text(
                encoding="utf-8"
            ),
            existing_course_json,
        )

    def test_admin_dashboard_and_create_page_still_work(self) -> None:
        admin_response = self.client.get("/admin")
        create_response = self.client.get("/admin/courses/new")

        self.assertEqual(admin_response.status_code, 200)
        self.assertIn("Управление курсами", admin_response.text)
        self.assertEqual(create_response.status_code, 200)
        self.assertIn("Создание курса", create_response.text)

    def test_missing_upload_id_is_rejected(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        review_data.pop("upload_id")

        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса", response.text)
        self.assertIn("Не указан загруженный файл", response.text)

    def test_resolve_upload_unit_tests(self) -> None:
        service = AdminUploadService(self.upload_dir)
        saved = service.save_upload("notes.pdf", b"%PDF unit test")

        resolved = service.resolve_upload(saved.upload_id)
        self.assertEqual(resolved.upload_id, saved.upload_id)
        self.assertEqual(resolved.source_path, saved.stored_path)
        self.assertEqual(resolved.extension, ".pdf")

        with self.assertRaises(AdminReviewError):
            service.resolve_upload("not-a-valid-id")

        saved.stored_path.unlink()
        with self.assertRaises(AdminReviewError):
            service.resolve_upload(saved.upload_id)


if __name__ == "__main__":
    unittest.main()
