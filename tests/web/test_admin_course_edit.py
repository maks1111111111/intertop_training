"""Tests for admin course metadata editing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_course_edit_service import (
    AdminCourseEditError,
    AdminCourseEditRequest,
    AdminCourseEditService,
    _resolve_course_json_path,
)
from tests.web.test_web_ui import _create_test_app, _write_course


def _write_course_with_custom_fields(
    courses_dir: Path,
    slug: str = "custom-course",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": "Custom Course",
                "description": "Original description",
                "status": "published",
                "language": "ru",
                "slug": slug,
                "custom_future_field": {"x": 1},
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
                "title": "Lesson one",
                "order": 1,
                "description": "Body text.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_course_with_quiz(courses_dir: Path, slug: str = "quiz-course") -> None:
    _write_course(courses_dir, slug, title="Quiz Course")
    quiz = {
        "id": f"{slug}_quiz",
        "title": "Итоговый тест",
        "passing_score": 80,
        "randomize_options": False,
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Question?",
                "options": [
                    {"id": "a", "text": "Wrong"},
                    {"id": "b", "text": "Right"},
                ],
                "correct_option_ids": ["b"],
            }
        ],
    }
    (courses_dir / slug / "quiz.json").write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class AdminCourseEditPageTests(unittest.TestCase):
    """Verify admin course metadata edit HTTP endpoints."""

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

    def test_get_edit_page_returns_200_for_existing_course(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Редактирование курса", response.text)

    def test_edit_page_prefills_fields(self) -> None:
        _write_course(
            self.courses_dir,
            "alpha",
            title="Alpha Course",
            description="Alpha description",
            language="kk",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha/edit")
        html = response.text

        self.assertIn('value="Alpha Course"', html)
        self.assertIn("Alpha description", html)
        self.assertIn('value="kk"', html)
        self.assertIn("Қазақша", html)

    def test_unknown_slug_returns_404(self) -> None:
        response = self.client.get("/admin/courses/missing-course/edit")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_post_valid_edit_redirects_with_prg(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "Updated Title",
                "description": "Updated description",
                "language": "en",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/admin/courses/alpha")

    def test_title_update_persists_to_course_json(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Renamed Course",
                "description": "Original description",
                "language": "ru",
            },
        )

        payload = json.loads(
            (self.courses_dir / "custom-course" / "course.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["title"], "Renamed Course")

    def test_description_update_persists(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Custom Course",
                "description": "New description",
                "language": "ru",
            },
        )

        payload = json.loads(
            (self.courses_dir / "custom-course" / "course.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["description"], "New description")

    def test_language_update_persists(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Custom Course",
                "description": "Original description",
                "language": "en",
            },
        )

        payload = json.loads(
            (self.courses_dir / "custom-course" / "course.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["language"], "en")

    def test_student_course_reflects_updated_values(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "Student Visible Title",
                "description": "Student visible description",
                "language": "ru",
            },
        )

        response = self.client.get("/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Student Visible Title", response.text)
        self.assertIn("Student visible description", response.text)

    def test_admin_detail_reflects_updated_values(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "Admin Visible Title",
                "description": "Admin visible description",
                "language": "ru",
            },
        )

        response = self.client.get("/admin/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Admin Visible Title", response.text)
        self.assertIn("Admin visible description", response.text)

    def test_slug_and_directory_unchanged_when_title_changes(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Completely Different Title",
                "description": "Original description",
                "language": "ru",
            },
        )

        self.assertTrue((self.courses_dir / "custom-course").is_dir())
        payload = json.loads(
            (self.courses_dir / "custom-course" / "course.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["slug"], "custom-course")

    def test_unknown_course_json_fields_are_preserved(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Updated Custom Course",
                "description": "Updated description",
                "language": "kk",
            },
        )

        payload = json.loads(
            (self.courses_dir / "custom-course" / "course.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["custom_future_field"], {"x": 1})

    def test_status_is_preserved(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Updated Custom Course",
                "description": "Updated description",
                "language": "ru",
            },
        )

        payload = json.loads(
            (self.courses_dir / "custom-course" / "course.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["status"], "published")

    def test_quiz_json_is_untouched(self) -> None:
        _write_course_with_quiz(self.courses_dir, "quiz-course")
        original_quiz = (
            self.courses_dir / "quiz-course" / "quiz.json"
        ).read_text(encoding="utf-8")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quiz-course/edit",
            data={
                "title": "Updated Quiz Course",
                "description": "Updated",
                "language": "ru",
            },
        )

        updated_quiz = (
            self.courses_dir / "quiz-course" / "quiz.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(original_quiz, updated_quiz)

    def test_lesson_files_are_untouched(self) -> None:
        _write_course_with_custom_fields(self.courses_dir)
        original_lesson = (
            self.courses_dir / "custom-course" / "lesson_01" / "lesson.json"
        ).read_text(encoding="utf-8")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/custom-course/edit",
            data={
                "title": "Updated Custom Course",
                "description": "Updated description",
                "language": "ru",
            },
        )

        updated_lesson = (
            self.courses_dir / "custom-course" / "lesson_01" / "lesson.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(original_lesson, updated_lesson)

    def test_empty_title_is_rejected(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "   ",
                "description": "Still here",
                "language": "ru",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Название курса обязательно", response.text)

        payload = json.loads(
            (self.courses_dir / "alpha" / "course.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["title"], "Alpha Course")

    def test_invalid_language_is_rejected(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "Alpha Course",
                "description": "Description",
                "language": "auto",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("поддерживаемый язык", response.text.lower())

    def test_no_filesystem_paths_in_html(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha/edit")

        self.assertNotIn(str(self.courses_dir), response.text)

    def test_editing_course_a_does_not_modify_course_b(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        _write_course(self.courses_dir, "beta", title="Beta Course")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "Alpha Updated",
                "description": "Alpha only",
                "language": "ru",
            },
        )

        beta_payload = json.loads(
            (self.courses_dir / "beta" / "course.json").read_text(encoding="utf-8")
        )
        self.assertEqual(beta_payload["title"], "Beta Course")

    def test_admin_detail_contains_edit_link(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")

        self.assertIn('href="/admin/courses/alpha/edit"', response.text)
        self.assertIn("Редактировать", response.text)

    def test_admin_dashboard_still_works(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Управление курсами", response.text)

    @patch("app.web.admin_course_edit_service.RuntimeRefreshService.refresh")
    def test_runtime_refresh_called_after_successful_write(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        mock_refresh.return_value = MagicMock()
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "Refreshed Title",
                "description": "Refreshed",
                "language": "ru",
            },
        )

        mock_refresh.assert_called_once()

    @patch("app.web.admin_course_edit_service.RuntimeRefreshService.refresh")
    def test_runtime_refresh_not_called_after_validation_failure(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/alpha/edit",
            data={
                "title": "",
                "description": "Refreshed",
                "language": "ru",
            },
        )

        mock_refresh.assert_not_called()

    @patch("app.web.admin_course_edit_service.RuntimeRefreshService.refresh")
    def test_malformed_course_json_returns_safe_error(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()
        course_json = self.courses_dir / "alpha" / "course.json"
        malformed = "{not valid json"
        course_json.write_text(malformed, encoding="utf-8")

        with patch.object(self.app.state.content_runtime, "_ensure_fresh"):
            response = self.client.post(
                "/admin/courses/alpha/edit",
                data={
                    "title": "Updated Title",
                    "description": "Updated description",
                    "language": "ru",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить метаданные курса.", response.text)
        self.assertEqual(course_json.read_text(encoding="utf-8"), malformed)
        mock_refresh.assert_not_called()

    @patch("app.web.admin_course_edit_service.RuntimeRefreshService.refresh")
    def test_unreadable_course_json_returns_safe_error(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()
        course_json = self.courses_dir / "alpha" / "course.json"

        with patch.object(
            Path,
            "read_text",
            side_effect=OSError("permission denied"),
        ):
            response = self.client.post(
                "/admin/courses/alpha/edit",
                data={
                    "title": "Updated Title",
                    "description": "Updated description",
                    "language": "ru",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить метаданные курса.", response.text)
        mock_refresh.assert_not_called()
        self.assertTrue(course_json.is_file())


class AdminCourseEditServiceTests(unittest.TestCase):
    """Direct tests for admin course edit service behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminCourseEditService(self.courses_dir, self.runtime)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_traversal_like_slug_is_rejected(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.runtime.refresh()

        with self.assertRaises(AdminCourseEditError):
            self.service.update_metadata(
                AdminCourseEditRequest(
                    slug="../alpha",
                    title="Bad",
                    description="",
                    language="ru",
                )
            )

    def test_resolve_course_json_rejects_nested_slug(self) -> None:
        nested = self.courses_dir / "nested" / "course"
        nested.mkdir(parents=True)
        (nested / "course.json").write_text("{}", encoding="utf-8")

        with self.assertRaises(AdminCourseEditError):
            _resolve_course_json_path(self.courses_dir, "nested/course")

    def test_malformed_course_json_raises_safe_error(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        course_json = self.courses_dir / "alpha" / "course.json"
        malformed = "{not valid json"
        course_json.write_text(malformed, encoding="utf-8")
        self.runtime.refresh()

        with self.assertRaises(AdminCourseEditError) as ctx:
            self.service.update_metadata(
                AdminCourseEditRequest(
                    slug="alpha",
                    title="Updated Title",
                    description="Updated description",
                    language="ru",
                )
            )

        self.assertEqual(
            ctx.exception.message,
            "Не удалось загрузить метаданные курса.",
        )
        self.assertEqual(course_json.read_text(encoding="utf-8"), malformed)

    @patch("app.web.admin_course_edit_service.RuntimeRefreshService.refresh")
    def test_read_failure_raises_safe_error_without_refresh(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.runtime.refresh()
        course_json = self.courses_dir / "alpha" / "course.json"

        with patch.object(
            Path,
            "read_text",
            side_effect=OSError("permission denied"),
        ):
            with self.assertRaises(AdminCourseEditError) as ctx:
                self.service.update_metadata(
                    AdminCourseEditRequest(
                        slug="alpha",
                        title="Updated Title",
                        description="Updated description",
                        language="ru",
                    )
                )

        self.assertEqual(
            ctx.exception.message,
            "Не удалось загрузить метаданные курса.",
        )
        mock_refresh.assert_not_called()
        self.assertTrue(course_json.is_file())


if __name__ == "__main__":
    unittest.main()
