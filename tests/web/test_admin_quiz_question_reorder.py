"""Tests for admin quiz question reordering."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_quiz_question_reorder_service import (
    AdminQuizQuestionReorderError,
    AdminQuizQuestionReorderRequest,
    AdminQuizQuestionReorderService,
)
from tests.web.test_admin_quiz_edit import _write_rich_quiz
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
)


def _move_up_url(
    slug: str = "rich-quiz-course",
    question_id: str = "q2",
) -> str:
    return f"/admin/courses/{slug}/quiz/questions/{question_id}/move-up"


def _move_down_url(
    slug: str = "rich-quiz-course",
    question_id: str = "q1",
) -> str:
    return f"/admin/courses/{slug}/quiz/questions/{question_id}/move-down"


def _write_three_question_quiz(courses_dir: Path, slug: str = "rich-quiz-course") -> None:
    """Create a course quiz with three ordered questions for reorder tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir(parents=True, exist_ok=True)
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
        json.dumps({"title": "Only lesson", "order": 1, "description": "Body text."}),
        encoding="utf-8",
    )
    quiz = {
        "id": f"{slug}_quiz",
        "title": "Итоговый тест",
        "passing_score": 80,
        "version": 2,
        "randomize_questions": False,
        "randomize_options": False,
        "custom_future_field": {"x": 1},
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "First question?",
                "options": [
                    {"id": "a", "text": "A1"},
                    {"id": "b", "text": "B1"},
                ],
                "correct_option_ids": ["b"],
            },
            {
                "id": "q2",
                "type": "single_choice",
                "text": "Second question?",
                "options": [
                    {"id": "c", "text": "C2"},
                    {"id": "d", "text": "D2"},
                ],
                "correct_option_ids": ["d"],
            },
            {
                "id": "q3",
                "type": "single_choice",
                "text": "Third question?",
                "options": [
                    {"id": "e", "text": "E3"},
                    {"id": "f", "text": "F3"},
                ],
                "correct_option_ids": ["f"],
            },
        ],
    }
    (course_dir / "quiz.json").write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class AdminQuizQuestionReorderPageTests(unittest.TestCase):
    """Verify reorder controls on the quiz edit page."""

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

    def test_quiz_edit_shows_reorder_buttons(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/move-up", response.text)
        self.assertIn("/move-down", response.text)

    def test_first_question_move_up_disabled(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn('questions/q1/move-up', response.text)
        self.assertIn("disabled", response.text)

    def test_last_question_move_down_disabled(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        self.assertIn('questions/q3/move-down', response.text)


class AdminQuizQuestionReorderPostTests(unittest.TestCase):
    """Verify admin quiz question reorder POST behavior."""

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

    def _question_ids(self, slug: str = "rich-quiz-course") -> list[str]:
        payload = json.loads(self._quiz_path(slug).read_text(encoding="utf-8"))
        return [item["id"] for item in payload["questions"]]

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_move_middle_up_changes_order(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = deepcopy(json.loads(self._quiz_path().read_text(encoding="utf-8")))
        response = self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/rich-quiz-course/quiz/edit",
        )
        self.assertEqual(self._question_ids(), ["q2", "q1", "q3"])
        refresh_mock.assert_called_once()
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["questions"][2], before["questions"][2])

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_move_middle_down_changes_order(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = deepcopy(json.loads(self._quiz_path().read_text(encoding="utf-8")))
        response = self.client.post(_move_down_url(question_id="q2"), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self._question_ids(), ["q1", "q3", "q2"])
        refresh_mock.assert_called_once()
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["questions"][0], before["questions"][0])

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_move_first_up_is_noop(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = self._quiz_path().read_text(encoding="utf-8")
        response = self.client.post(_move_up_url(question_id="q1"), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), before)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_move_last_down_is_noop(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = self._quiz_path().read_text(encoding="utf-8")
        response = self.client.post(
            _move_down_url(question_id="q3"),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), before)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_question_ids_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        payload = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        ids = {item["id"] for item in payload["questions"]}
        self.assertEqual(ids, {"q1", "q2", "q3"})

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_quiz_metadata_preserved(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["title"], before["title"])
        self.assertEqual(after["passing_score"], before["passing_score"])
        self.assertEqual(after["randomize_questions"], before["randomize_questions"])
        self.assertEqual(after["randomize_options"], before["randomize_options"])
        self.assertEqual(after["custom_future_field"], before["custom_future_field"])

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_other_question_content_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        after = json.loads(self._quiz_path().read_text(encoding="utf-8"))
        self.assertEqual(after["questions"][2], before["questions"][2])

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_course_json_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = self._course_json_path().read_text(encoding="utf-8")
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        self.assertEqual(self._course_json_path().read_text(encoding="utf-8"), before)

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_lesson_json_unchanged(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = self._lesson_json_path().read_text(encoding="utf-8")
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        self.assertEqual(self._lesson_json_path().read_text(encoding="utf-8"), before)

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_get_page_reflects_new_order(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        response = self.client.get("/admin/courses/rich-quiz-course/quiz/edit")
        first_pos = response.text.index("Second question?")
        second_pos = response.text.index("First question?")
        self.assertLess(first_pos, second_pos)

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_student_quiz_still_opens(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        self.assertEqual(response.status_code, 200)

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_student_quiz_shows_new_order(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        response = self.client.get("/courses/rich-quiz-course/quiz")
        first_pos = response.text.index("Second question?")
        second_pos = response.text.index("First question?")
        self.assertLess(first_pos, second_pos)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.post(
            _move_up_url("missing-course"),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_course_without_quiz_returns_404(self) -> None:
        _write_course(self.courses_dir, "no-quiz")
        response = self.client.post(
            _move_up_url("no-quiz"),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Тест не найден", response.text)

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_unknown_question_shows_error_on_edit_page(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = self._quiz_path().read_text(encoding="utf-8")
        response = self.client.post(
            _move_up_url(question_id="missing-q"),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Вопрос не найден", response.text)
        self.assertIn("Настройка итогового теста", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), before)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_traversal_like_slug_rejected(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        response = self.client.post(
            "/admin/courses/../rich-quiz-course/quiz/questions/q2/move-up",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_malformed_quiz_json_safe_error(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        quiz_path = self._quiz_path()
        quiz_path.write_text("{not json", encoding="utf-8")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        response = self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить данные теста", response.text)
        self.assertEqual(quiz_path.read_text(encoding="utf-8"), "{not json")
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_reorder_service._atomic_write_json")
    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_write_failure_safe_error(
        self,
        refresh_mock: MagicMock,
        write_mock: MagicMock,
    ) -> None:
        _write_three_question_quiz(self.courses_dir)
        before = self._quiz_path().read_text(encoding="utf-8")
        write_mock.side_effect = OSError("disk full")
        response = self.client.post(_move_up_url(question_id="q2"), follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сохранить изменения", response.text)
        self.assertEqual(self._quiz_path().read_text(encoding="utf-8"), before)
        refresh_mock.assert_not_called()

    @patch("app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh")
    def test_no_filesystem_path_in_error_html(self, refresh_mock: MagicMock) -> None:
        _write_three_question_quiz(self.courses_dir)
        response = self.client.post(
            _move_up_url(question_id="missing-q"),
            follow_redirects=False,
        )
        self.assertNotIn(str(self.courses_dir), response.text)
        self.assertNotIn("/tmp/", response.text)


class AdminQuizQuestionReorderServiceTests(unittest.TestCase):
    """Direct unit tests for AdminQuizQuestionReorderService."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _service(self) -> AdminQuizQuestionReorderService:
        runtime = ContentRuntime(self.courses_dir)
        runtime.refresh()
        return AdminQuizQuestionReorderService(self.courses_dir, runtime)

    def test_service_move_up_swaps_questions(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        service = self._service()
        with patch(
            "app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh"
        ) as refresh_mock:
            result = service.move_up(
                AdminQuizQuestionReorderRequest(slug="rich-quiz-course", question_id="q2")
            )
        self.assertTrue(result.changed)
        payload = json.loads(
            (self.courses_dir / "rich-quiz-course" / "quiz.json").read_text(encoding="utf-8")
        )
        self.assertEqual([item["id"] for item in payload["questions"]], ["q2", "q1", "q3"])
        refresh_mock.assert_called_once()

    def test_service_move_down_swaps_questions(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        service = self._service()
        with patch(
            "app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh"
        ) as refresh_mock:
            result = service.move_down(
                AdminQuizQuestionReorderRequest(slug="rich-quiz-course", question_id="q2")
            )
        self.assertTrue(result.changed)
        payload = json.loads(
            (self.courses_dir / "rich-quiz-course" / "quiz.json").read_text(encoding="utf-8")
        )
        self.assertEqual([item["id"] for item in payload["questions"]], ["q1", "q3", "q2"])
        refresh_mock.assert_called_once()

    def test_service_move_up_first_returns_unchanged(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        service = self._service()
        with patch(
            "app.web.admin_quiz_question_reorder_service.RuntimeRefreshService.refresh"
        ) as refresh_mock:
            result = service.move_up(
                AdminQuizQuestionReorderRequest(slug="rich-quiz-course", question_id="q1")
            )
        self.assertFalse(result.changed)
        refresh_mock.assert_not_called()

    def test_service_rejects_traversal_question_id(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        service = self._service()
        with self.assertRaises(AdminQuizQuestionReorderError) as ctx:
            service.move_up(
                AdminQuizQuestionReorderRequest(slug="rich-quiz-course", question_id="../other")
            )
        self.assertIn("Некорректный идентификатор вопроса", ctx.exception.message)

    def test_service_rejects_traversal_slug(self) -> None:
        _write_three_question_quiz(self.courses_dir)
        service = self._service()
        with self.assertRaises(AdminQuizQuestionReorderError) as ctx:
            service.move_up(
                AdminQuizQuestionReorderRequest(slug="../rich-quiz-course", question_id="q2")
            )
        self.assertIn("Некорректный идентификатор курса", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
