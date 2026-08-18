"""Tests for admin course generation from the review step."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.lesson_builder import LessonCandidate
from app.web.admin_generation_service import (
    AdminGenerationError,
    AdminGenerationRequest,
    AdminGenerationService,
    AdminGenerationSuccess,
)
from app.web.admin_upload_service import (
    AdminCourseFormValues,
    AdminUploadService,
    _web_form_to_generation_options,
)
from tests.web.test_admin_course_upload import _default_form_data
from tests.web.test_admin_course_generation_review import (
    _extract_hidden_value,
)
from tests.web.test_web_ui import _authenticate_test_web_user
from tests.web.test_web_ui import _create_test_app, _write_course


def _write_generated_course(
    courses_dir: Path,
    slug: str = "generated-course",
    *,
    title: str = "Новый курс",
    description: str = "Описание тестового курса",
    with_quiz: bool = True,
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": title,
                "description": description,
                "language": "ru",
                "slug": slug,
                "status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps(
            {
                "order": 1,
                "title": "First lesson",
                "description": "Body text.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if with_quiz:
        (course_dir / "quiz.json").write_text(
            json.dumps({"title": "Quiz", "passing_score": 80, "questions": []}),
            encoding="utf-8",
        )


class AdminCourseGenerationReviewFormTests(unittest.TestCase):
    """Verify the review page exposes a functional generation form."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _post_upload(self) -> tuple[str, dict[str, str]]:
        data = dict(_default_form_data())
        files = {
            "source_file": ("source.pdf", b"%PDF-1.4 test", "application/octet-stream")
        }
        confirm = self.client.post("/admin/courses/new", data=data, files=files)
        self.assertEqual(confirm.status_code, 200)
        html = confirm.text
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
        review = self.client.post("/admin/courses/new/review", data=review_data)
        self.assertEqual(review.status_code, 200)
        return review.text, review_data

    def test_review_page_contains_generation_form(self) -> None:
        html, _review_data = self._post_upload()

        self.assertIn('action="/admin/courses/new/loading"', html)
        self.assertIn('name="upload_id"', html)
        self.assertIn('type="submit"', html)
        self.assertIn("Создать курс", html)
        self.assertNotIn('aria-disabled="true"', html)
        self.assertNotIn("disabled", html.split("Создать курс")[0][-120:])

    def test_review_page_generation_form_posts_to_loading_endpoint(self) -> None:
        html, _review_data = self._post_upload()

        self.assertIn('id="admin-generation-form"', html)
        self.assertIn('method="post"', html)
        self.assertIn('action="/admin/courses/new/loading"', html)
        self.assertIn('name="upload_id"', html)
        self.assertIn('id="admin-generate-submit"', html)
        self.assertNotIn('action="/admin/courses/new/generate"', html)


class AdminCourseGenerationHttpTests(unittest.TestCase):
    """HTTP-level tests for POST /admin/courses/new/generate."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.upload_dir = self.app.state.upload_dir
        self.mock_generation_service = MagicMock(spec=AdminGenerationService)
        self.app.state.admin_generation_service = self.mock_generation_service
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _generation_form_data(
        self,
        upload_id: str,
        *,
        extra: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        data = dict(_default_form_data())
        data["upload_id"] = upload_id
        data["original_filename"] = "source.pdf"
        if extra:
            data.update(extra)
        return data

    def test_generation_post_invokes_service_with_upload_id(self) -> None:
        upload_service = AdminUploadService(self.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        self.mock_generation_service.generate_course.return_value = (
            AdminGenerationSuccess(
                slug="generated-course",
                title="Новый курс",
                lessons_count=1,
                has_quiz=True,
                course_url="/courses/generated-course",
                admin_url="/admin",
                manage_url="/admin/courses/generated-course",
            )
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data(saved.upload_id),
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/generated-course/created",
        )
        self.mock_generation_service.generate_course.assert_called_once()
        request = self.mock_generation_service.generate_course.call_args.args[0]
        self.assertIsInstance(request, AdminGenerationRequest)
        self.assertEqual(request.upload_id, saved.upload_id)
        self.assertEqual(request.form_values.course_title, "Новый курс")

    def test_generation_post_never_accepts_stored_path(self) -> None:
        upload_service = AdminUploadService(self.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        data = self._generation_form_data(saved.upload_id)
        data["stored_path"] = str(saved.stored_path)

        self.mock_generation_service.generate_course.return_value = (
            AdminGenerationSuccess(
                slug="generated-course",
                title="Новый курс",
                lessons_count=1,
                has_quiz=False,
                course_url="/courses/generated-course",
                admin_url="/admin",
                manage_url="/admin/courses/generated-course",
            )
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=data,
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        request = self.mock_generation_service.generate_course.call_args.args[0]
        self.assertEqual(request.upload_id, saved.upload_id)

    def test_malformed_upload_id_fails_safely(self) -> None:
        self.mock_generation_service.generate_course.side_effect = AdminGenerationError(
            "Недействительный идентификатор загрузки."
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data("../../etc/passwd"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Недействительный идентификатор загрузки", response.text)

    def test_stale_upload_id_fails_safely(self) -> None:
        self.mock_generation_service.generate_course.side_effect = AdminGenerationError(
            "Загруженный файл не найден. Загрузите файл заново."
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data("a" * 32),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Загруженный файл не найден", response.text)

    def test_invalid_generation_options_fail_safely(self) -> None:
        upload_service = AdminUploadService(self.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        self.mock_generation_service.generate_course.side_effect = AdminGenerationError(
            "Некорректные параметры генерации. Проверьте форму и попробуйте снова."
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data(
                saved.upload_id,
                extra={"lesson_count": "0"},
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Некорректные параметры генерации", response.text)

    def test_success_page_renders_after_redirect(self) -> None:
        app, db_tmp, _db_path, upload_tmp = _create_test_app(self.courses_dir)
        client = TestClient(app)
        _write_generated_course(self.courses_dir, "generated-course")
        app.state.content_runtime.refresh()

        response = client.get("/admin/courses/generated-course/created")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Курс создан", html)
        self.assertIn("Новый курс", html)
        self.assertIn("Уроков", html)
        self.assertIn("Итоговый тест", html)
        self.assertIn('href="/courses/generated-course"', html)
        self.assertIn('href="/admin"', html)
        self.assertIn("Управлять курсом", html)
        self.assertIn('href="/admin/courses/generated-course"', html)
        upload_tmp.cleanup()
        db_tmp.cleanup()

    def test_generated_course_is_accessible_without_restart(self) -> None:
        app, db_tmp, _db_path, upload_tmp = _create_test_app(self.courses_dir)
        client = TestClient(app)
        _authenticate_test_web_user(app)
        _write_generated_course(self.courses_dir, "generated-course")
        app.state.content_runtime.refresh()

        response = client.get("/courses/generated-course")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Новый курс", response.text)
        upload_tmp.cleanup()
        db_tmp.cleanup()

    def test_failed_generation_does_not_advertise_success(self) -> None:
        upload_service = AdminUploadService(self.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        self.mock_generation_service.generate_course.side_effect = AdminGenerationError(
            "Не удалось создать курс. Проверьте исходный файл и параметры и попробуйте снова."
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data(saved.upload_id),
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Курс создан", response.text)
        self.assertEqual(list(self.courses_dir.iterdir()), [])

    def test_generation_error_renders_review_page_with_loading_state_reset(self) -> None:
        upload_service = AdminUploadService(self.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        self.mock_generation_service.generate_course.side_effect = AdminGenerationError(
            "Не удалось создать курс. Проверьте исходный файл и параметры и попробуйте снова."
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data(saved.upload_id),
        )

        html = response.text
        self.assertIn("Не удалось создать курс", html)
        self.assertIn('action="/admin/courses/new/loading"', html)
        self.assertIn("Создать курс", html)

    def test_no_source_path_in_generation_html(self) -> None:
        upload_service = AdminUploadService(self.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        self.mock_generation_service.generate_course.side_effect = AdminGenerationError(
            "Не удалось создать курс. Проверьте исходный файл и параметры и попробуйте снова."
        )

        response = self.client.post(
            "/admin/courses/new/generate",
            data=self._generation_form_data(saved.upload_id),
        )

        self.assertNotIn(str(saved.stored_path.resolve()), response.text)

    @patch("app.web.router.AdminGenerationService")
    def test_router_does_not_call_openai_directly(
        self,
        mock_service_cls: MagicMock,
    ) -> None:
        app, db_tmp, _db_path, upload_tmp = _create_test_app(self.courses_dir)
        mock_instance = MagicMock(spec=AdminGenerationService)
        mock_instance.generate_course.return_value = AdminGenerationSuccess(
            slug="generated-course",
            title="Новый курс",
            lessons_count=1,
            has_quiz=False,
            course_url="/courses/generated-course",
            admin_url="/admin",
            manage_url="/admin/courses/generated-course",
        )
        app.state.admin_generation_service = mock_instance
        client = TestClient(app)

        upload_service = AdminUploadService(app.state.upload_dir)
        saved = upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        data = dict(_default_form_data())
        data["upload_id"] = saved.upload_id
        data["original_filename"] = "source.pdf"

        with patch("app.ai.openai_client.OpenAIClient") as mock_openai:
            response = client.post(
                "/admin/courses/new/generate",
                data=data,
                follow_redirects=False,
            )
            mock_openai.assert_not_called()

        self.assertEqual(response.status_code, 303)
        upload_tmp.cleanup()
        db_tmp.cleanup()

    def test_admin_pages_still_work(self) -> None:
        admin_response = self.client.get("/admin")
        create_response = self.client.get("/admin/courses/new")

        self.assertEqual(admin_response.status_code, 200)
        self.assertIn("Управление курсами", admin_response.text)
        self.assertEqual(create_response.status_code, 200)
        self.assertIn("Создание курса", create_response.text)


class AdminGenerationServiceUnitTests(unittest.TestCase):
    """Unit tests for AdminGenerationService orchestration."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.upload_dir = Path(self.tmp.name) / "uploads"
        self.upload_dir.mkdir()
        self.upload_service = AdminUploadService(self.upload_dir)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.runtime = self.app.state.content_runtime

        self.mock_importer = MagicMock()
        self.mock_text_service = MagicMock()
        self.mock_course_with_quiz = MagicMock()

        self.service = AdminGenerationService(
            upload_service=self.upload_service,
            courses_dir=self.courses_dir,
            runtime=self.runtime,
            importer=self.mock_importer,
            text_generation_service=self.mock_text_service,
            course_with_quiz_service=self.mock_course_with_quiz,
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _saved_upload(self) -> tuple[str, AdminCourseFormValues]:
        saved = self.upload_service.save_upload("source.pdf", b"%PDF-1.4 test")
        form_values = AdminCourseFormValues(
            course_title="Новый курс",
            description="Описание администратора",
            source_language="ru",
            output_language="ru",
            lesson_count="5",
            lesson_size="medium",
            difficulty="beginner",
            generate_quiz=True,
            include_practical_tasks=False,
            include_checklists=False,
            include_explanations=True,
        )
        return saved.upload_id, form_values

    def test_successful_generation_refreshes_runtime_and_persists_description(self) -> None:
        upload_id, form_values = self._saved_upload()
        lesson = LessonCandidate(title="Lesson one", content="Content.")
        self.mock_importer.read_source.return_value = "Imported text"
        self.mock_text_service.generate_from_text.return_value = LessonGenerationResult(
            lessons=[lesson],
            course=GeneratedCourseMetadata(
                language="ru",
                title="AI title",
                description="AI description",
            ),
        )

        course_dir = self.courses_dir / "generated-course"
        course_dir.mkdir()
        (course_dir / "course.json").write_text(
            json.dumps(
                {
                    "title": "Новый курс",
                    "description": "Описание администратора",
                    "language": "ru",
                    "slug": "generated-course",
                }
            ),
            encoding="utf-8",
        )
        workflow_result = MagicMock()
        workflow_result.course_directory = course_dir
        workflow_result.quiz_path = course_dir / "quiz.json"
        self.mock_course_with_quiz.generate_and_persist.return_value = workflow_result

        result = self.service.generate_course(
            AdminGenerationRequest(
                upload_id=upload_id,
                form_values=form_values,
                original_filename="source.pdf",
            )
        )

        self.assertEqual(result.slug, "generated-course")
        self.assertEqual(result.title, "Новый курс")
        self.assertTrue(result.has_quiz)

        persist_call = self.mock_course_with_quiz.generate_and_persist.call_args
        lesson_result = persist_call.args[0]
        self.assertEqual(
            lesson_result.course.description,
            "Описание администратора",
        )
        self.assertEqual(lesson_result.course.title, "Новый курс")
        self.assertEqual(
            persist_call.kwargs["generate_quiz"],
            True,
        )
        self.assertEqual(
            persist_call.kwargs["questions_per_lesson"],
            0,
        )
        self.mock_text_service.generate_from_text.assert_called_once_with(
            "Imported text",
            output_language="ru",
        )
        self.assertEqual(
            persist_call.kwargs["output_language"],
            "ru",
        )

    def test_web_form_uses_adaptive_quiz_not_fixed_three(self) -> None:
        upload_id, form_values = self._saved_upload()
        resolved = self.upload_service.resolve_upload(upload_id)
        options = _web_form_to_generation_options(resolved.source_path, form_values)

        self.assertTrue(options.generate_quiz)
        self.assertEqual(options.questions_per_lesson, 0)

    def test_missing_upload_id_raises_safe_error(self) -> None:
        _upload_id, form_values = self._saved_upload()

        with self.assertRaises(AdminGenerationError) as ctx:
            self.service.generate_course(
                AdminGenerationRequest(
                    upload_id="not-valid",
                    form_values=form_values,
                    original_filename="source.pdf",
                )
            )

        self.assertIn("идентификатор", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
