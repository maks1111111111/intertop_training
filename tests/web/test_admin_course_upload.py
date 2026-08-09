"""Tests for admin course source file upload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional

from fastapi.testclient import TestClient

from tests.web.test_web_ui import _create_test_app, _write_course


def _default_form_data() -> dict[str, str]:
    return {
        "course_title": "Новый курс",
        "description": "Описание тестового курса",
        "source_language": "ru",
        "output_language": "ru",
        "lesson_count": "5",
        "lesson_size": "medium",
        "difficulty": "beginner",
        "include_explanations": "1",
    }


class AdminCourseUploadTests(unittest.TestCase):
    """Verify safe source file upload in the course creation wizard."""

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
        filename: str,
        content: bytes,
        *,
        form_data: Optional[dict] = None,
    ):
        data = dict(_default_form_data())
        if form_data:
            data.update(form_data)
        files = {"source_file": (filename, content, "application/octet-stream")}
        return self.client.post("/admin/courses/new", data=data, files=files)

    def test_valid_pdf_upload_succeeds(self) -> None:
        response = self._post_upload("source.pdf", b"%PDF-1.4 test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Файл загружен", response.text)
        self.assertIn("source.pdf", response.text)
        self.assertIn("PDF", response.text)
        self.assertIn("Новый курс", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)

    def test_valid_docx_upload_succeeds(self) -> None:
        response = self._post_upload("material.docx", b"PK docx content")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DOCX", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)

    def test_valid_pptx_upload_succeeds(self) -> None:
        response = self._post_upload("slides.pptx", b"PK pptx content")
        self.assertEqual(response.status_code, 200)
        self.assertIn("PPTX", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)

    def test_valid_mp4_upload_succeeds(self) -> None:
        response = self._post_upload("video.mp4", b"\x00\x00\x00\x20ftypmp42")
        self.assertEqual(response.status_code, 200)
        self.assertIn("MP4", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)

    def test_unsupported_extension_is_rejected(self) -> None:
        response = self._post_upload("notes.txt", b"plain text")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Неподдерживаемый формат файла", response.text)
        self.assertIn("Создание курса", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 0)

    def test_empty_upload_is_rejected(self) -> None:
        response = self._post_upload("empty.pdf", b"")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Файл пуст", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 0)

    def test_missing_file_is_rejected(self) -> None:
        response = self.client.post("/admin/courses/new", data=_default_form_data())
        self.assertEqual(response.status_code, 200)
        self.assertIn("Файл не выбран", response.text)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 0)

    def test_path_traversal_filename_cannot_escape_upload_directory(self) -> None:
        response = self._post_upload("../../escape.pdf", b"%PDF traversal")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Файл загружен", response.text)

        stored_files = list(self.upload_dir.iterdir())
        self.assertEqual(len(stored_files), 1)
        stored_path = stored_files[0].resolve()
        upload_root = self.upload_dir.resolve()
        self.assertEqual(
            stored_path.parent,
            upload_root,
            "Uploaded file must remain inside the upload directory",
        )

    def test_get_create_page_still_works(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса", response.text)
        self.assertIn('name="source_file"', response.text)

    def test_no_course_is_generated(self) -> None:
        before = list(self.courses_dir.iterdir())
        response = self._post_upload("source.pdf", b"%PDF-1.4 test")
        self.assertEqual(response.status_code, 200)
        after = list(self.courses_dir.iterdir())
        self.assertEqual(before, after)

    def test_no_published_course_files_are_written(self) -> None:
        _write_course(self.courses_dir, "existing")
        existing_course_json = (
            self.courses_dir / "existing" / "course.json"
        ).read_text(encoding="utf-8")
        course_dirs_before = {
            path.name for path in self.courses_dir.iterdir() if path.is_dir()
        }

        response = self._post_upload("source.pdf", b"%PDF-1.4 test")
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

    def test_confirm_page_has_edit_and_continue_actions(self) -> None:
        response = self._post_upload("source.pdf", b"%PDF-1.4 test")
        self.assertIn('href="/admin/courses/new"', response.text)
        self.assertIn("Назад к редактированию", response.text)
        self.assertIn("Продолжить", response.text)
        self.assertIn('action="/admin/courses/new/review"', response.text)
        self.assertIn('name="upload_id"', response.text)

    def test_admin_dashboard_still_works(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Управление курсами", response.text)


if __name__ == "__main__":
    unittest.main()
