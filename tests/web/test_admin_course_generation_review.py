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
        self.assertIn("Начальный", html)
        self.assertIn("Средний", html)
        self.assertIn("Пояснения", html)
        self.assertNotIn("Source Language", html)
        self.assertNotIn("Include Explanations", html)
        self.assertIn("Создать курс", html)
        self.assertIn("Проверьте параметры и нажмите «Создать курс»", html)
        self.assertIn('action="/admin/courses/new/loading"', html)

    def _review_page_html(self) -> str:
        _confirm_html, review_data = self._upload_and_extract_state()
        response = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_review_page_posts_to_loading_endpoint(self) -> None:
        html = self._review_page_html()

        self.assertIn('id="admin-generation-form"', html)
        self.assertIn('method="post"', html)
        self.assertIn('action="/admin/courses/new/loading"', html)
        self.assertIn('name="upload_id"', html)
        self.assertIn('id="admin-generate-submit"', html)
        self.assertNotIn('action="/admin/courses/new/generate"', html)

    def _loading_page_html(self) -> str:
        _confirm_html, review_data = self._upload_and_extract_state()
        response = self.client.post("/admin/courses/new/loading", data=review_data)
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_loading_page_contains_ai_generation_state(self) -> None:
        html = self._loading_page_html()

        self.assertIn('id="admin-ai-generation-loading"', html)
        self.assertIn("AI создаёт ваш курс", html)
        self.assertIn(
            "Анализируем документ и формируем структуру обучения",
            html,
        )
        self.assertIn("admin-ai-generation-orbit", html)
        self.assertIn("admin-ai-generation-loading-page", html)
        self.assertIn('id="admin-ai-generation-status"', html)
        self.assertIn("admin-ai-generation-stepper", html)
        self.assertIn("admin-ai-generation-card", html)
        self.assertIn("admin-ai-generation-hero", html)
        self.assertIn("admin-ai-generation-progress", html)
        self.assertIn("admin-ai-generation-ellipsis", html)

    def test_loading_page_shows_generation_stages(self) -> None:
        html = self._loading_page_html()

        self.assertIn("Анализ документа", html)
        self.assertIn("Построение структуры", html)
        self.assertIn("Создание уроков", html)
        self.assertIn("Практические задания", html)
        self.assertIn("Создание теста", html)
        self.assertIn("Финальная проверка", html)
        self.assertIn("admin-ai-generation-step--active", html)
        self.assertIn("admin-ai-generation-step--pending", html)
        self.assertIn(
            "AI анализирует содержание документа",
            html,
        )
        self.assertIn(
            "Не закрывайте страницу. После завершения курс откроется автоматически.",
            html,
        )
        self.assertNotIn("Что происходит?", html)
        self.assertNotIn("admin-ai-generation-step-desc", html)

    def test_loading_page_skips_optional_steps_when_disabled(self) -> None:
        html = self._loading_page_html()

        self.assertIn('data-generation-step="practical"', html)
        self.assertIn('data-generation-step="quiz"', html)
        self.assertIn("admin-ai-generation-step--skipped", html)
        self.assertIn('data-include-practical-tasks="false"', html)
        self.assertIn('data-generate-quiz="false"', html)

    def test_loading_page_progress_starts_at_twelve_percent(self) -> None:
        html = self._loading_page_html()

        self.assertIn('aria-valuenow="12"', html)
        self.assertIn(">12%</span>", html)
        self.assertNotIn("завершено", html)
        self.assertIn('style="width: 12%;"', html)
        self.assertIn("data-generation-step=", html)
        self.assertIn("setProgress(95)", html)
        self.assertIn("showGenerationSuccess(", html)
        self.assertIn("setProgress(100, true)", html)
        self.assertNotRegex(html, r"setProgress\(100\)(?!,\s*true)")
        self.assertIn("Формируем оптимальную структуру курса", html)
        self.assertIn("Создаём уроки и учебные материалы", html)
        self.assertIn("Выполняем финальную проверку и сохранение", html)

    def test_loading_page_includes_optional_steps_when_enabled(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        review_data["generate_quiz"] = "1"
        review_data["include_practical_tasks"] = "1"
        response = self.client.post("/admin/courses/new/loading", data=review_data)
        self.assertEqual(response.status_code, 200)
        html = response.text

        self.assertIn('data-include-practical-tasks="true"', html)
        self.assertIn('data-generate-quiz="true"', html)
        self.assertIn('name="generate_quiz"', html)
        self.assertIn('name="include_practical_tasks"', html)
        self.assertNotIn(
            'data-generation-step="practical" class="admin-ai-generation-step admin-ai-generation-step--skipped"',
            html,
        )

    def test_loading_page_uses_vertical_stepper_not_numbered_list(self) -> None:
        html = self._loading_page_html()

        self.assertIn("admin-ai-generation-step-label", html)
        self.assertNotRegex(html, r"<ol[^>]*>\s*<li>\s*1\.")
        self.assertNotIn('type="1"', html)

    def test_loading_page_shows_decorative_progress_bar(self) -> None:
        html = self._loading_page_html()

        self.assertIn("admin-ai-generation-progress-bar", html)
        self.assertIn("admin-ai-generation-progress-track", html)
        self.assertIn('role="progressbar"', html)
        self.assertIn('aria-valuenow="12"', html)
        self.assertIn("function setProgress(percent, allowComplete)", html)

    def test_loading_page_starts_async_fetch_generation(self) -> None:
        html = self._loading_page_html()

        self.assertIn('action="/admin/courses/new/generate"', html)
        self.assertIn('name="upload_id"', html)
        self.assertIn('name="original_filename"', html)
        self.assertIn('name="course_title"', html)
        self.assertIn("fetch(", html)
        self.assertIn("new FormData(form)", html)
        self.assertIn("response.redirected", html)
        self.assertIn("showGenerationSuccess(response.url)", html)
        self.assertIn("Курс успешно создан", html)
        self.assertIn("admin-ai-generation-progress-bar--success", html)
        self.assertIn("window.setTimeout(function ()", html)
        self.assertNotIn("window.location.assign(response.url);", html)
        self.assertNotIn("form.submit()", html)
        self.assertIn("generationStarted", html)
        self.assertIn("startGeneration()", html)
        self.assertIn(
            "Не удалось завершить создание курса. Проверьте соединение и попробуйте снова.",
            html,
        )
        self.assertIn("document.open()", html)

    def test_loading_page_preserves_all_hidden_form_fields(self) -> None:
        html = self._loading_page_html()

        self.assertIn('name="source_language"', html)
        self.assertIn('name="output_language"', html)
        self.assertIn('name="lesson_count"', html)
        self.assertIn('name="lesson_size"', html)
        self.assertIn('name="difficulty"', html)
        self.assertIn('name="include_explanations"', html)

    def test_invalid_upload_id_on_loading_is_rejected(self) -> None:
        _confirm_html, review_data = self._upload_and_extract_state()
        review_data["upload_id"] = "a" * 32

        response = self.client.post("/admin/courses/new/loading", data=review_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создание курса", response.text)
        self.assertIn("Загруженный файл не найден", response.text)

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
