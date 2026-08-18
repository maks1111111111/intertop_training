"""Tests for admin quiz question editing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_quiz_edit_service import AdminQuizEditError
from app.web.admin_quiz_question_edit_service import (
    AdminQuizQuestionEditError,
    AdminQuizQuestionEditRequest,
    AdminQuizQuestionEditService,
    parse_question_tags,
)
from tests.web.test_admin_quiz_edit import _write_rich_quiz
from tests.web.test_web_ui import _authenticate_test_web_user
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
)


def _question_edit_url(slug: str = "rich-quiz-course", question_id: str = "q1") -> str:
    return f"/admin/courses/{slug}/quiz/questions/{question_id}/edit"


def _valid_post_data(**overrides):
    data = {
        "text": "Updated question text?",
        "option_text_0": "Updated wrong",
        "option_text_1": "Updated right",
        "correct_option_id": "b",
        "explanation": "Updated explanation.",
        "lesson": "lesson_01",
        "difficulty": "3",
        "tags": "updated\ntag-two",
    }
    data.update(overrides)
    return data


class AdminQuizQuestionEditPageTests(unittest.TestCase):
    """Verify admin quiz question edit GET endpoints."""

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

    def test_existing_question_returns_200(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertEqual(response.status_code, 200)

    def test_page_contains_heading(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn("Редактирование вопроса", response.text)

    def test_question_text_prefilled(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn("First rich question?", response.text)

    def test_option_texts_prefilled(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn("Wrong one", response.text)
        self.assertIn("Right one", response.text)

    def test_correct_radio_selected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        block = response.text.split('id="correct-b"')[1][:120]
        self.assertIn("checked", block)

    def test_explanation_prefilled(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn("Because B is correct.", response.text)

    def test_lesson_prefilled(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn('value="lesson_01"', response.text)
        self.assertIn("selected", response.text.split('value="lesson_01"')[1][:40])

    def test_difficulty_prefilled(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn('name="difficulty"', response.text)
        self.assertIn('value="2"', response.text)

    def test_tags_prefilled(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertIn("basics", response.text)
        self.assertIn("intro", response.text)

    def test_quiz_edit_page_has_edit_button(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("Редактировать", response.text)
        self.assertIn("/quiz/questions/q1/edit", response.text)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.get(_question_edit_url("missing-course"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_no_quiz_returns_404(self) -> None:
        _write_course(self.courses_dir, "no-quiz")
        response = self.client.get(_question_edit_url("no-quiz"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Тест не найден", response.text)

    def test_unknown_question_returns_404(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url(question_id="missing-q"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Вопрос не найден", response.text)

    def test_no_filesystem_path_in_html(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_question_edit_url())
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)


class AdminQuizQuestionEditPostTests(unittest.TestCase):
    """Verify admin quiz question edit POST behavior."""

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

    def _course_json_path(self, slug: str = "rich-quiz-course") -> Path:
        return self.courses_dir / slug / "course.json"

    def _lesson_json_path(self, slug: str = "rich-quiz-course") -> Path:
        return self.courses_dir / slug / "lesson_01" / "lesson.json"

    def _post_valid(self, question_id: str = "q1", **overrides):
        return self.client.post(
            _question_edit_url(question_id=question_id),
            data=_valid_post_data(**overrides),
            follow_redirects=False,
        )

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_valid_update_returns_303(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(response.status_code, 303)
        refresh_mock.assert_called_once()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_valid_update_redirects_to_quiz_edit(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/rich-quiz-course/quiz/edit",
        )

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_question_text_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["text"], "Updated question text?")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_option_texts_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        options = payload["questions"][0]["options"]
        self.assertEqual(options[0]["text"], "Updated wrong")
        self.assertEqual(options[1]["text"], "Updated right")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_correct_option_ids_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid(correct_option_id="a")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["correct_option_ids"], ["a"])

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_explanation_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["explanation"], "Updated explanation.")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_lesson_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["lesson"], "lesson_01")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_difficulty_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["difficulty"], 3)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_tags_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["tags"], ["updated", "tag-two"])

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_question_id_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["id"], "q1")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_type_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["type"], "single_choice")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_option_ids_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        original_ids = [option["id"] for option in original["questions"][0]["options"]]
        updated_ids = [option["id"] for option in payload["questions"][0]["options"]]
        self.assertEqual(updated_ids, original_ids)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_option_count_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(len(payload["questions"][0]["options"]), 2)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_other_question_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][1], original["questions"][1])

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_ai_context_preserved(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][0]["ai_context"], "hidden context")

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_unknown_question_field_preserved(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        payload["questions"][0]["custom_future_field"] = {"y": 2}
        self._quiz_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        self._post_valid()
        updated = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(updated["questions"][0]["custom_future_field"], {"y": 2})

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_unknown_quiz_root_field_preserved(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["custom_future_field"], {"x": 1})

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_quiz_settings_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["title"], original["title"])
        self.assertEqual(payload["passing_score"], original["passing_score"])
        self.assertEqual(payload["randomize_questions"], original["randomize_questions"])
        self.assertEqual(payload["randomize_options"], original["randomize_options"])

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_course_json_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._course_json_path().read_text(encoding="utf-8")
        self._post_valid()
        self.assertEqual(self._course_json_path().read_text(encoding="utf-8"), original)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_lesson_json_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._lesson_json_path().read_text(encoding="utf-8")
        self._post_valid()
        self.assertEqual(self._lesson_json_path().read_text(encoding="utf-8"), original)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_student_quiz_still_opens(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertEqual(response.status_code, 200)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_student_quiz_shows_updated_text(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertIn("Updated question text?", response.text)

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_blank_question_text_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._quiz_path().read_text(encoding="utf-8")
        response = self._post_valid(text="   ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Текст вопроса обязателен.", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_blank_option_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._quiz_path().read_text(encoding="utf-8")
        response = self._post_valid(option_text_0=" ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Текст каждого варианта ответа обязателен.", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_invalid_correct_option_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._quiz_path().read_text(encoding="utf-8")
        response = self._post_valid(correct_option_id="z")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите один правильный вариант ответа.", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_no_correct_answer_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        data = _valid_post_data()
        del data["correct_option_id"]
        response = self.client.post(
            _question_edit_url(),
            data=data,
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите один правильный вариант ответа.", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_invalid_lesson_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._quiz_path().read_text(encoding="utf-8")
        response = self._post_valid(lesson="lesson_99")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите урок из текущего курса.", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_difficulty_abc_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(difficulty="abc")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Сложность должна быть целым числом от 0 до 5.", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_difficulty_minus_one_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(difficulty="-1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Сложность должна быть целым числом от 0 до 5.", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_difficulty_six_rejected(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(difficulty="6")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Сложность должна быть целым числом от 0 до 5.", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_malformed_quiz_json_safe_error(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        original = "{not-json"
        self._quiz_path().write_text(original, encoding="utf-8")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить данные теста.", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    @patch(
        "app.web.admin_quiz_question_edit_service._load_quiz_json_payload",
        side_effect=AdminQuizEditError("Не удалось загрузить данные теста."),
    )
    def test_unreadable_quiz_safe_error(
        self,
        load_mock: MagicMock,
        refresh_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)
        original = self._quiz_path().read_text(encoding="utf-8")
        response = self._post_valid()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить данные теста.", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), original)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    @patch(
        "app.web.admin_quiz_question_edit_service._atomic_write_json",
        side_effect=OSError("write failed"),
    )
    def test_write_failure_safe_error(
        self,
        write_mock: MagicMock,
        refresh_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сохранить изменения", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_edit_service.RuntimeRefreshService.refresh")
    def test_no_path_in_error_html(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid(text="")
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)


class AdminQuizQuestionEditServiceTests(unittest.TestCase):
    """Direct unit tests for admin quiz question edit service."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_quiz(self.courses_dir)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminQuizQuestionEditService(self.courses_dir, self.runtime)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_traversal_slug_rejected(self) -> None:
        with self.assertRaises(AdminQuizQuestionEditError) as ctx:
            self.service.update_question(
                AdminQuizQuestionEditRequest(
                    slug="../escape",
                    question_id="q1",
                    text="Question?",
                    option_texts=("A", "B"),
                    correct_option_id="a",
                    explanation="",
                    lesson="",
                    difficulty=1,
                    tags=[],
                )
            )
        self.assertIn("Некорректный идентификатор курса", ctx.exception.message)

    def test_traversal_question_id_rejected(self) -> None:
        with self.assertRaises(AdminQuizQuestionEditError) as ctx:
            self.service.update_question(
                AdminQuizQuestionEditRequest(
                    slug="rich-quiz-course",
                    question_id="../other",
                    text="Question?",
                    option_texts=("A", "B"),
                    correct_option_id="a",
                    explanation="",
                    lesson="",
                    difficulty=1,
                    tags=[],
                )
            )
        self.assertIn("Некорректный идентификатор вопроса", ctx.exception.message)

    def test_parse_question_tags_strips_empty_lines(self) -> None:
        self.assertEqual(parse_question_tags("one\n\n two \n"), ["one", "two"])

    def test_get_edit_view_none_for_missing_question(self) -> None:
        self.assertIsNone(self.service.get_edit_view("rich-quiz-course", "missing"))


class AdminQuizQuestionEditRegressionTests(unittest.TestCase):
    """Regression checks for related admin and student routes."""

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

    def test_admin_dashboard_still_works(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)

    def test_student_course_page_still_works(self) -> None:
        _authenticate_test_web_user(self.client.app)
        _write_course_with_quiz(self.courses_dir, "quiz-course")
        response = self.client.get("/courses/quiz-course")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
