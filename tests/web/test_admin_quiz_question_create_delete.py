"""Tests for admin quiz question creation and deletion."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_quiz_question_create_service import (
    AdminQuizQuestionCreateError,
    AdminQuizQuestionCreateRequest,
    AdminQuizQuestionCreateService,
    AdminQuizQuestionDeleteRequest,
    _next_question_id,
)
from tests.web.test_admin_quiz_edit import _write_rich_quiz
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
)


def _create_url(slug: str = "rich-quiz-course") -> str:
    return f"/admin/courses/{slug}/quiz/questions/new"


def _delete_url(
    slug: str = "rich-quiz-course",
    question_id: str = "q1",
) -> str:
    return f"/admin/courses/{slug}/quiz/questions/{question_id}/delete"


def _valid_create_data(**overrides):
    data = {
        "text": "Brand new question?",
        "option_text_0": "Option A",
        "option_text_1": "Option B",
        "option_text_2": "Option C",
        "option_text_3": "Option D",
        "correct_option_index": "1",
        "explanation": "Because B.",
        "lesson": "lesson_01",
        "difficulty": "2",
        "tags": "new\ntag",
    }
    data.update(overrides)
    return data


class AdminQuizQuestionCreatePageTests(unittest.TestCase):
    """Verify admin quiz question create GET endpoints."""

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

    def test_get_new_returns_200(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_create_url())
        self.assertEqual(response.status_code, 200)

    def test_form_renders_four_answer_options(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get(_create_url())
        self.assertIn('name="option_text_0"', response.text)
        self.assertIn('name="option_text_1"', response.text)
        self.assertIn('name="option_text_2"', response.text)
        self.assertIn('name="option_text_3"', response.text)

    def test_course_without_quiz_returns_404(self) -> None:
        _write_course(self.courses_dir, "no-quiz")
        response = self.client.get(_create_url("no-quiz"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Тест не найден", response.text)

    def test_missing_course_returns_404(self) -> None:
        response = self.client.get(_create_url("missing-course"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_quiz_edit_has_add_question_button(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn("Добавить вопрос", response.text)
        self.assertIn("/quiz/questions/new", response.text)


class AdminQuizQuestionCreatePostTests(unittest.TestCase):
    """Verify admin quiz question create POST behavior."""

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

    def _post_valid(self, slug: str = "rich-quiz-course", **overrides):
        return self.client.post(
            _create_url(slug),
            data=_valid_create_data(**overrides),
            follow_redirects=False,
        )

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_valid_create_returns_303(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(response.status_code, 303)
        refresh_mock.assert_called_once()

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_valid_create_redirects_to_quiz_edit(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_valid()
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/rich-quiz-course/quiz/edit",
        )

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_creates_q3_when_q1_q2_exist(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(len(payload["questions"]), 3)
        self.assertEqual(payload["questions"][-1]["id"], "q3")

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_q1_q2_q5_creates_q6(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        payload["questions"].append(
            {
                "id": "q5",
                "type": "single_choice",
                "text": "Gap question?",
                "options": [
                    {"id": "a", "text": "A"},
                    {"id": "b", "text": "B"},
                ],
                "correct_option_ids": ["a"],
            }
        )
        self._quiz_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._post_valid()
        updated = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(updated["questions"][-1]["id"], "q6")

    def test_nonstandard_ids_do_not_break_sequence(self) -> None:
        questions = [
            {"id": "custom-x"},
            {"id": "q2"},
            {"id": "q10"},
        ]
        self.assertEqual(_next_question_id(questions), "q11")

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_new_question_has_single_choice_type(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["type"], "single_choice")

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_new_question_has_four_options(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(len(payload["questions"][-1]["options"]), 4)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_new_question_option_ids_abcd(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        option_ids = [item["id"] for item in payload["questions"][-1]["options"]]
        self.assertEqual(option_ids, ["a", "b", "c", "d"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_correct_option_ids_exactly_one(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid(correct_option_index="2")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["correct_option_ids"], ["c"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_text_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["text"], "Brand new question?")

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_option_texts_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        texts = [item["text"] for item in payload["questions"][-1]["options"]]
        self.assertEqual(texts, ["Option A", "Option B", "Option C", "Option D"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_explanation_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["explanation"], "Because B.")

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_lesson_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["lesson"], "lesson_01")

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_difficulty_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["difficulty"], 2)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_tags_persisted(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["tags"], ["new", "tag"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_existing_questions_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        before = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        original_q1 = deepcopy(before["questions"][0])
        original_q2 = deepcopy(before["questions"][1])
        self._post_valid()
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["questions"][0], original_q1)
        self.assertEqual(after["questions"][1], original_q2)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_quiz_settings_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        before = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_valid()
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["title"], before["title"])
        self.assertEqual(after["passing_score"], before["passing_score"])
        self.assertEqual(after["randomize_questions"], before["randomize_questions"])
        self.assertEqual(after["randomize_options"], before["randomize_options"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_unknown_quiz_root_field_preserved(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["custom_future_field"], {"x": 1})

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_course_json_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        before = self._course_json_path().read_text(encoding="utf-8")
        self._post_valid()
        after = self._course_json_path().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_lesson_json_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        before = self._lesson_json_path().read_text(encoding="utf-8")
        self._post_valid()
        after = self._lesson_json_path().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_blank_question_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.post(_create_url(), data=_valid_create_data(text="   "))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Текст вопроса обязателен.", response.text)

    def test_blank_option_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.post(
            _create_url(),
            data=_valid_create_data(option_text_2="  "),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Текст каждого варианта ответа обязателен.", response.text)

    def test_invalid_correct_index_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.post(
            _create_url(),
            data=_valid_create_data(correct_option_index="9"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите один правильный вариант ответа.", response.text)

    def test_invalid_lesson_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.post(
            _create_url(),
            data=_valid_create_data(lesson="lesson_99"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите урок из текущего курса.", response.text)

    def test_invalid_difficulty_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self.client.post(
            _create_url(),
            data=_valid_create_data(difficulty="abc"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Сложность должна быть целым числом от 0 до 5.", response.text)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_malformed_quiz_safe_error(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._quiz_path().write_text("{bad", encoding="utf-8")
        response = self._post_valid()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить данные теста.", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_create_service._atomic_write_json")
    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_write_failure_safe_error(
        self,
        refresh_mock: MagicMock,
        write_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)
        write_mock.side_effect = OSError("disk full")
        response = self._post_valid()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сохранить изменения.", response.text)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_student_quiz_still_opens_after_creation(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertEqual(response.status_code, 200)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_new_question_visible_to_student(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_valid()
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertIn("Brand new question?", response.text)


class AdminQuizQuestionDeleteTests(unittest.TestCase):
    """Verify admin quiz question delete POST behavior."""

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

    def _post_delete(self, question_id: str = "q1", slug: str = "rich-quiz-course"):
        return self.client.post(
            _delete_url(slug, question_id),
            follow_redirects=False,
        )

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_valid_delete_removes_selected_question(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_delete("q1")
        self.assertEqual(response.status_code, 303)
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(len(payload["questions"]), 1)
        self.assertEqual(payload["questions"][0]["id"], "q2")
        refresh_mock.assert_called_once()

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_deleting_q1_leaves_q2(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_delete("q1")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["questions"]], ["q2"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_deleting_q2_leaves_q1(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_delete("q2")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["questions"]], ["q1"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_other_question_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        before = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        original_q2 = deepcopy(before["questions"][1])
        self._post_delete("q1")
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["questions"][0], original_q2)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_quiz_settings_unchanged_on_delete(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        before = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self._post_delete("q1")
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["title"], before["title"])
        self.assertEqual(after["passing_score"], before["passing_score"])

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_unknown_fields_preserved_on_delete(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_delete("q1")
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(payload["custom_future_field"], {"x": 1})

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_course_and_lesson_files_unchanged_on_delete(
        self,
        refresh_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)
        course_before = self._course_json_path().read_text(encoding="utf-8")
        lesson_before = self._lesson_json_path().read_text(encoding="utf-8")
        self._post_delete("q1")
        self.assertEqual(self._course_json_path().read_text(encoding="utf-8"), course_before)
        self.assertEqual(self._lesson_json_path().read_text(encoding="utf-8"), lesson_before)

    def test_missing_question_safe_error(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_delete("missing-q")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Вопрос не найден", response.text)

    def test_cannot_delete_last_remaining_question(self) -> None:
        _write_course_with_quiz(self.courses_dir, "single-q-course")
        quiz_path = self.courses_dir / "single-q-course" / "quiz.json"
        payload = json.loads(quiz_path.read_text(encoding="utf-8"))
        payload["questions"] = [payload["questions"][0]]
        quiz_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        response = self.client.post(
            _delete_url("single-q-course", "q1"),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("В тесте должен остаться хотя бы один вопрос.", response.text)
        updated = json.loads(quiz_path.read_text(encoding="utf-8"))
        self.assertEqual(len(updated["questions"]), 1)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_refresh_not_called_on_rejected_delete(self, refresh_mock: MagicMock) -> None:
        _write_course_with_quiz(self.courses_dir, "single-q-course")
        quiz_path = self.courses_dir / "single-q-course" / "quiz.json"
        payload = json.loads(quiz_path.read_text(encoding="utf-8"))
        payload["questions"] = [payload["questions"][0]]
        quiz_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        self.client.post(_delete_url("single-q-course", "q1"))
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_successful_delete_redirects_303(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_delete("q1")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/rich-quiz-course/quiz/edit",
        )

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_student_quiz_still_opens_after_delete(self, refresh_mock: MagicMock) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_delete("q1")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertEqual(response.status_code, 200)

    @patch("app.web.admin_quiz_question_create_service.RuntimeRefreshService.refresh")
    def test_deleted_question_absent_from_student_quiz(
        self,
        refresh_mock: MagicMock,
    ) -> None:
        _write_rich_quiz(self.courses_dir)
        self._post_delete("q1")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertNotIn("First rich question?", response.text)
        self.assertIn("Second rich question?", response.text)

    def test_traversal_like_question_id_rejected(self) -> None:
        _write_rich_quiz(self.courses_dir)
        runtime = ContentRuntime(self.courses_dir)
        service = AdminQuizQuestionCreateService(self.courses_dir, runtime)
        with self.assertRaises(AdminQuizQuestionCreateError) as ctx:
            service.delete_question(
                AdminQuizQuestionDeleteRequest(slug="rich-quiz-course", question_id="../other")
            )
        self.assertIn("Некорректный идентификатор вопроса.", ctx.exception.message)

    def test_no_filesystem_path_in_error_html(self) -> None:
        _write_rich_quiz(self.courses_dir)
        response = self._post_delete("missing-q")
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)


class AdminQuizQuestionCreateServiceUnitTests(unittest.TestCase):
    """Direct service-level tests for question id generation and validation."""

    def test_next_question_id_empty_list_returns_q1(self) -> None:
        self.assertEqual(_next_question_id([]), "q1")

    def test_traversal_slug_rejected_by_service(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        courses_dir = Path(tmp.name)
        runtime = ContentRuntime(courses_dir)
        service = AdminQuizQuestionCreateService(courses_dir, runtime)
        with self.assertRaises(AdminQuizQuestionCreateError) as ctx:
            service.create_question(
                AdminQuizQuestionCreateRequest(
                    slug="../escape",
                    text="Q?",
                    option_texts=("A", "B", "C", "D"),
                    correct_option_index=0,
                    explanation="",
                    lesson="",
                    difficulty=0,
                    tags=[],
                )
            )
        self.assertIn("идентификатор курса", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
