"""Tests for admin quiz settings editing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_quiz_edit_service import (
    AdminQuizEditError,
    AdminQuizEditRequest,
    AdminQuizEditService,
    _resolve_quiz_json_path,
)
from tests.web.test_web_ui import _authenticate_test_web_user
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
    _write_empty_course,
)


def _write_rich_quiz(
    courses_dir: Path,
    slug: str = "rich-quiz-course",
) -> None:
    """Create a course with a quiz that has rich metadata for admin tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": "Rich Quiz Course",
                "description": "Course with detailed quiz.",
                "status": "published",
                "language": "ru",
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
                "title": "Only lesson",
                "order": 1,
                "description": "Body text.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    quiz = {
        "id": f"{slug}_quiz",
        "title": "Итоговый тест",
        "passing_score": 80,
        "version": 2,
        "randomize_questions": True,
        "randomize_options": False,
        "custom_future_field": {"x": 1},
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "First rich question?",
                "options": [
                    {"id": "a", "text": "Wrong one"},
                    {"id": "b", "text": "Right one"},
                ],
                "correct_option_ids": ["b"],
                "explanation": "Because B is correct.",
                "lesson": "lesson_01",
                "difficulty": 2,
                "tags": ["basics", "intro"],
                "ai_context": "hidden context",
            },
            {
                "id": "q2",
                "type": "single_choice",
                "text": "Second rich question?",
                "options": [
                    {"id": "c", "text": "Also wrong"},
                    {"id": "d", "text": "Also right"},
                ],
                "correct_option_ids": ["d"],
            },
        ],
    }
    (course_dir / "quiz.json").write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class AdminQuizEditPageTests(unittest.TestCase):
    """Verify admin quiz edit HTTP endpoints."""

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

    def test_get_edit_page_returns_200_for_existing_quiz(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertEqual(response.status_code, 200)

    def test_page_contains_heading(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("Настройка итогового теста", response.text)

    def test_prefilled_title(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn('value="Итоговый тест"', response.text)

    def test_prefilled_passing_score(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn('value="80"', response.text)

    def test_randomize_questions_checkbox_checked(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn('id="quiz-randomize-questions"', response.text)
        self.assertIn("checked", response.text.split("quiz-randomize-questions")[1][:120])

    def test_randomize_options_checkbox_unchecked(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        block = response.text.split('id="quiz-randomize-options"')[1][:120]
        self.assertNotIn("checked", block)

    def test_questions_visible(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("First rich question?", response.text)
        self.assertIn("Second rich question?", response.text)

    def test_options_visible(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("Wrong one", response.text)
        self.assertIn("Right one", response.text)

    def test_correct_option_identified(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("Правильный ответ", response.text)
        self.assertIn("admin-quiz-option--correct", response.text)

    def test_explanation_lesson_tags_render(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("Because B is correct.", response.text)
        self.assertIn("lesson_01", response.text)
        self.assertIn("basics", response.text)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.get("/admin/courses/missing-course/quiz/edit")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_course_without_quiz_returns_404(self) -> None:
        _write_course(self.courses_dir, "no-quiz")
        response = self.client.get("/admin/courses/no-quiz/quiz/edit")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Тест не найден", response.text)

    def test_no_absolute_path_in_html(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)

    def test_admin_detail_has_manage_test_button(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course")
        self.assertIn("Управлять тестом", response.text)
        self.assertIn("/admin/courses/rich-quiz-course/quiz/edit", response.text)

    def test_admin_detail_no_manage_button_without_quiz(self) -> None:
        _write_course(self.courses_dir, "plain-course")
        response = self.client.get("/admin/courses/plain-course")
        self.assertNotIn("Управлять тестом", response.text)


class AdminQuizEditPostTests(unittest.TestCase):
    """Verify admin quiz edit POST behavior."""

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

    def _quiz_path(self, slug: str = "rich-quiz-course") -> Path:
        return self.courses_dir / slug / "quiz.json"

    def _post_valid(self, slug: str = "rich-quiz-course", **overrides):
        data = {
            "title": "Обновлённый тест",
            "passing_score": "75",
            "randomize_questions": "1",
            "randomize_options": "1",
        }
        data.update(overrides)
        return self.client.post(
            f"/admin/courses/{slug}/quiz/edit",
            data=data,
            follow_redirects=False,
        )

    def test_valid_update_returns_303(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(response.status_code, 303)

    def test_valid_update_redirects_to_detail(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(response.headers["location"], "/admin/courses/rich-quiz-course")

    def test_title_persisted(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["title"], "Обновлённый тест")

    def test_passing_score_persisted(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["passing_score"], 75)

    def test_randomize_questions_persisted(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid(randomize_questions="1")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertTrue(payload["randomize_questions"])

    def test_randomize_options_persisted(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid(randomize_options="1")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertTrue(payload["randomize_options"])

    def test_quiz_id_preserved(self) -> None:
        _write_rich_quiz(self.courses_dir)
        original = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["id"], original["id"])

    def test_quiz_version_preserved(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 2)

    def test_questions_unchanged(self) -> None:
        _write_rich_quiz(self.courses_dir)
        original = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"], original["questions"])

    def test_correct_option_ids_unchanged(self) -> None:
        _write_rich_quiz(self.courses_dir)
        original = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        for before, after in zip(original["questions"], payload["questions"]):
            self.assertEqual(before["correct_option_ids"], after["correct_option_ids"])

    def test_unknown_future_field_preserved(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["custom_future_field"], {"x": 1})

    def test_student_quiz_accessible_after_edit(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertEqual(response.status_code, 200)

    def test_student_quiz_shows_updated_title(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertIn("Обновлённый тест", response.text)

    def test_admin_detail_reflects_updated_passing_score(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        response = self.client.get("/admin/courses/rich-quiz-course")
        self.assertIn("75%", response.text)

    @patch("app.web.admin_quiz_edit_service.RuntimeRefreshService.refresh")
    def test_runtime_refresh_called_after_success(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        refresh_mock.assert_called_once()

    def test_empty_title_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(title="   ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Название теста обязательно.", response.text)

    def test_noninteger_passing_score_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(passing_score="abc")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Проходной балл должен быть целым числом.", response.text)

    def test_passing_score_zero_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(passing_score="0")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Проходной балл должен быть от 1 до 100.", response.text)

    def test_passing_score_101_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(passing_score="101")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Проходной балл должен быть от 1 до 100.", response.text)

    def test_invalid_request_does_not_modify_quiz_json(self) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._quiz_path().read_text(encoding="utf-8")
        self._post_valid(title="")
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)

    @patch("app.web.admin_quiz_edit_service.RuntimeRefreshService.refresh")
    def test_invalid_request_does_not_refresh_runtime(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid(title="")
        refresh_mock.assert_not_called()

    def test_course_json_unchanged(self) -> None:
        _write_rich_quiz(self.courses_dir)
        original = (self.courses_dir / "rich-quiz-course" / "course.json").read_text(
            encoding="utf-8"
        )
        self._post_valid()
        current = (self.courses_dir / "rich-quiz-course" / "course.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(current, original)

    def test_lesson_json_unchanged(self) -> None:
        _write_rich_quiz(self.courses_dir)
        original = (
            self.courses_dir / "rich-quiz-course" / "lesson_01" / "lesson.json"
        ).read_text(encoding="utf-8")
        self._post_valid()
        current = (
            self.courses_dir / "rich-quiz-course" / "lesson_01" / "lesson.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(current, original)

    def test_admin_dashboard_still_works(self) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)

    def test_student_course_page_still_works(self) -> None:
        _authenticate_test_web_user(self.client.app)
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        response = self.client.get("/courses/rich-quiz-course")
        self.assertEqual(response.status_code, 200)


class AdminQuizEditServiceTests(unittest.TestCase):
    """Direct unit tests for AdminQuizEditService."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminQuizEditService(self.courses_dir, self.runtime)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_edit_view_reads_empty_draft_quiz_from_disk(self) -> None:
        _write_empty_course(self.courses_dir, "draft-quiz")
        quiz_path = self.courses_dir / "draft-quiz" / "quiz.json"
        quiz_path.write_text(
            json.dumps(
                {
                    "id": "draft-quiz_quiz",
                    "title": "Итоговый тест",
                    "passing_score": 80,
                    "version": 1,
                    "randomize_questions": True,
                    "randomize_options": True,
                    "questions": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.runtime.get_courses()

        course = self.runtime.get_course("draft-quiz")
        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.quiz)

        edit_view = self.service.get_edit_view("draft-quiz")
        self.assertIsNotNone(edit_view)
        assert edit_view is not None
        self.assertEqual(edit_view.questions_count, 0)
        self.assertEqual(edit_view.title, "Итоговый тест")

    def test_traversal_slug_rejected(self) -> None:
        with self.assertRaises(AdminQuizEditError):
            _resolve_quiz_json_path(self.courses_dir, "../escape")

    def test_nested_slug_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        with self.assertRaises(AdminQuizEditError):
            _resolve_quiz_json_path(self.courses_dir, "rich-quiz-course/nested")

    def test_malformed_quiz_json_safe_error(self) -> None:
        _write_rich_quiz(self.courses_dir)
        quiz_path = self.courses_dir / "rich-quiz-course" / "quiz.json"
        quiz_path.write_text("{not valid json", encoding="utf-8")
        original = quiz_path.read_text(encoding="utf-8")

        with self.assertRaises(AdminQuizEditError) as ctx:
            self.service.update_quiz(
                AdminQuizEditRequest(
                    slug="rich-quiz-course",
                    title="Title",
                    passing_score="80",
                    randomize_questions=True,
                    randomize_options=False,
                )
            )

        self.assertIn("Не удалось загрузить данные теста.", str(ctx.exception))
        self.assertEqual(quiz_path.read_text(encoding="utf-8"), original)

    @patch("app.web.admin_quiz_edit_service.RuntimeRefreshService.refresh")
    def test_malformed_quiz_json_does_not_refresh(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        quiz_path = self.courses_dir / "rich-quiz-course" / "quiz.json"
        quiz_path.write_text("{not valid json", encoding="utf-8")

        with self.assertRaises(AdminQuizEditError):
            self.service.update_quiz(
                AdminQuizEditRequest(
                    slug="rich-quiz-course",
                    title="Title",
                    passing_score="80",
                    randomize_questions=True,
                    randomize_options=False,
                )
            )

        refresh_mock.assert_not_called()

    @patch("pathlib.Path.read_text", side_effect=OSError("read failed"))
    @patch("app.web.admin_quiz_edit_service.RuntimeRefreshService.refresh")
    def test_unreadable_quiz_json_safe_error(
        self,
        refresh_mock: MagicMock,
        _read_text_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)

        with self.assertRaises(AdminQuizEditError) as ctx:
            self.service.update_quiz(
                AdminQuizEditRequest(
                    slug="rich-quiz-course",
                    title="Title",
                    passing_score="80",
                    randomize_questions=True,
                    randomize_options=False,
                )
            )

        self.assertIn("Не удалось загрузить данные теста.", str(ctx.exception))
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_edit_service._atomic_write_json", side_effect=OSError("write failed"))
    @patch("app.web.admin_quiz_edit_service.RuntimeRefreshService.refresh")
    def test_write_failure_safe_error(
        self,
        refresh_mock: MagicMock,
        _write_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)

        with self.assertRaises(AdminQuizEditError) as ctx:
            self.service.update_quiz(
                AdminQuizEditRequest(
                    slug="rich-quiz-course",
                    title="Title",
                    passing_score="80",
                    randomize_questions=True,
                    randomize_options=False,
                )
            )

        self.assertIn("Не удалось сохранить изменения.", str(ctx.exception))
        refresh_mock.assert_not_called()

    def test_stale_upload_id_style_slug_rejected(self) -> None:
        with self.assertRaises(AdminQuizEditError):
            self.service.update_quiz(
                AdminQuizEditRequest(
                    slug="missing-quiz-course",
                    title="Title",
                    passing_score="80",
                    randomize_questions=True,
                    randomize_options=False,
                )
            )


class AdminQuizEditRegressionTests(unittest.TestCase):
    """Regression checks for existing admin flows."""

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

    def test_existing_lesson_edit_still_works(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(
            "/admin/courses/rich-quiz-course/lessons/lesson_01/edit"
        )
        self.assertEqual(response.status_code, 200)

    def test_get_new_course_page_still_works(self) -> None:
        response = self.client.get("/admin/courses/new")
        self.assertEqual(response.status_code, 200)

    def test_error_html_has_no_absolute_path(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.post(
            "/admin/courses/rich-quiz-course/quiz/edit",
            data={"title": "", "passing_score": "80"},
        )
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)


if __name__ == "__main__":
    unittest.main()
