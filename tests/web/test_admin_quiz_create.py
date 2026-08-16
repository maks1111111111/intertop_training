"""Tests for admin quiz creation from scratch."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import ContentRuntimeManager
from app.services.runtime_refresh_service import RuntimeRefreshService
from app.web.admin_quiz_create_service import (
    AdminQuizCreateError,
    AdminQuizCreateService,
)
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
    _write_empty_course,
)


class AdminQuizCreateServiceTests(unittest.TestCase):
    """Unit tests for AdminQuizCreateService."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminQuizCreateService(self.courses_dir, self.runtime)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_quiz_writes_defaults(self) -> None:
        _write_empty_course(self.courses_dir, "manual-empty")

        result = self.service.create_quiz("manual-empty")
        quiz_json = json.loads(
            (self.courses_dir / "manual-empty" / "quiz.json").read_text(encoding="utf-8")
        )

        self.assertEqual(result.edit_url, "/admin/courses/manual-empty/quiz/edit")
        self.assertEqual(quiz_json["id"], "manual-empty_quiz")
        self.assertEqual(quiz_json["title"], "Итоговый тест")
        self.assertEqual(quiz_json["passing_score"], 80)
        self.assertTrue(quiz_json["randomize_questions"])
        self.assertTrue(quiz_json["randomize_options"])
        self.assertEqual(quiz_json["questions"], [])

    def test_create_quiz_existing_quiz_rejected(self) -> None:
        _write_course_with_quiz(self.courses_dir, "with-quiz")
        with self.assertRaises(AdminQuizCreateError) as ctx:
            self.service.create_quiz("with-quiz")
        self.assertEqual(ctx.exception.message, "Итоговый тест для этого курса уже создан.")

    def test_create_quiz_unknown_course_rejected(self) -> None:
        with self.assertRaises(AdminQuizCreateError) as ctx:
            self.service.create_quiz("missing-course")
        self.assertEqual(ctx.exception.message, "Курс не найден.")

    def test_create_quiz_traversal_slug_rejected(self) -> None:
        with self.assertRaises(AdminQuizCreateError):
            self.service.create_quiz("../escape")

    def test_create_quiz_refreshes_runtime(self) -> None:
        _write_empty_course(self.courses_dir, "refresh-me")
        with patch(
            "app.web.admin_quiz_create_service.RuntimeRefreshService"
        ) as refresh_cls:
            refresh = refresh_cls.return_value
            self.service.create_quiz("refresh-me")
            refresh.refresh.assert_called_once()

    def test_create_quiz_draft_is_not_exposed_in_runtime(self) -> None:
        _write_empty_course(self.courses_dir, "draft-quiz")
        self.runtime.get_courses()

        self.service.create_quiz("draft-quiz")

        course = self.runtime.get_course("draft-quiz")
        self.assertIsNotNone(course)
        self.assertIsNone(course.quiz)

    def test_first_question_updates_preloaded_runtime(self) -> None:
        _write_course(self.courses_dir, "runtime-quiz", language="ru")
        self.runtime.get_course("runtime-quiz")
        self.assertIsNone(self.runtime.get_course("runtime-quiz").quiz)

        self.service.create_quiz("runtime-quiz")
        self.assertIsNone(self.runtime.get_course("runtime-quiz").quiz)

        quiz_json_path = self.courses_dir / "runtime-quiz" / "quiz.json"
        payload = json.loads(quiz_json_path.read_text(encoding="utf-8"))
        payload["questions"] = [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Runtime question?",
                "options": [
                    {"id": "a", "text": "A"},
                    {"id": "b", "text": "B"},
                    {"id": "c", "text": "C"},
                    {"id": "d", "text": "D"},
                ],
                "correct_option_ids": ["a"],
                "explanation": "",
                "lesson": "lesson_01",
                "difficulty": 1,
                "tags": [],
            }
        ]
        quiz_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        RuntimeRefreshService(ContentRuntimeManager(self.runtime)).refresh()

        course = self.runtime.get_course("runtime-quiz")
        self.assertIsNotNone(course.quiz)
        self.assertEqual(len(course.quiz.questions), 1)
        self.assertEqual(course.quiz.questions[0].text, "Runtime question?")


class AdminQuizCreatePageTests(unittest.TestCase):
    """HTTP tests for quiz creation routes."""

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

    def test_course_detail_shows_create_quiz_button_when_missing(self) -> None:
        _write_empty_course(self.courses_dir, "no-quiz")
        response = self.client.get("/admin/courses/no-quiz")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Создать итоговый тест", response.text)
        self.assertIn('action="/admin/courses/no-quiz/quiz/create"', response.text)

    def test_course_detail_hides_create_quiz_button_when_quiz_exists(self) -> None:
        _write_course_with_quiz(self.courses_dir, "has-quiz")
        response = self.client.get("/admin/courses/has-quiz")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Создать итоговый тест", response.text)
        self.assertIn("Управлять тестом", response.text)

    def test_course_detail_shows_manage_button_for_empty_draft_quiz(self) -> None:
        _write_empty_course(self.courses_dir, "draft-only")
        self.client.post("/admin/courses/draft-only/quiz/create")

        response = self.client.get("/admin/courses/draft-only")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Создать итоговый тест", response.text)
        self.assertIn("Управлять тестом", response.text)
        self.assertIn("Тест: 0 вопросов", response.text)

    def test_learner_quiz_unavailable_for_empty_draft_quiz(self) -> None:
        _write_empty_course(self.courses_dir, "learner-draft")
        self.client.post("/admin/courses/learner-draft/quiz/create")

        response = self.client.get("/courses/learner-draft/quiz")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Тест недоступен", response.text)

    def test_learner_quiz_available_after_first_question_added(self) -> None:
        _write_course(self.courses_dir, "learner-ready", language="ru")
        self.client.post("/admin/courses/learner-ready/quiz/create")
        self.client.post(
            "/admin/courses/learner-ready/quiz/questions/new",
            data={
                "text": "Ready question?",
                "option_text_0": "A",
                "option_text_1": "B",
                "option_text_2": "C",
                "option_text_3": "D",
                "correct_option_index": "0",
                "explanation": "",
                "lesson": "lesson_01",
                "difficulty": "1",
                "tags": "",
            },
            follow_redirects=False,
        )

        response = self.client.get("/courses/learner-ready/quiz")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ready question?", response.text)

    def test_create_quiz_redirects_to_edit_page(self) -> None:
        _write_empty_course(self.courses_dir, "create-quiz")
        response = self.client.post(
            "/admin/courses/create-quiz/quiz/create",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/create-quiz/quiz/edit",
        )

    def test_empty_quiz_edit_page_works(self) -> None:
        _write_empty_course(self.courses_dir, "empty-quiz")
        self.client.post("/admin/courses/empty-quiz/quiz/create")

        response = self.client.get("/admin/courses/empty-quiz/quiz/edit")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Настройка итогового теста", response.text)
        self.assertIn("Всего вопросов: 0", response.text)
        self.assertIn("Добавить вопрос", response.text)

    def test_first_manual_question_can_be_created_for_empty_quiz(self) -> None:
        _write_course(self.courses_dir, "first-question", language="ru")
        self.client.post("/admin/courses/first-question/quiz/create")

        response = self.client.post(
            "/admin/courses/first-question/quiz/questions/new",
            data={
                "text": "First manual question?",
                "option_text_0": "A",
                "option_text_1": "B",
                "option_text_2": "C",
                "option_text_3": "D",
                "correct_option_index": "1",
                "explanation": "",
                "lesson": "lesson_01",
                "difficulty": "1",
                "tags": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/first-question/quiz/edit",
        )

        quiz_json = json.loads(
            (self.courses_dir / "first-question" / "quiz.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(quiz_json["questions"]), 1)
        self.assertEqual(quiz_json["questions"][0]["text"], "First manual question?")

    def test_second_create_quiz_does_not_overwrite_existing_quiz(self) -> None:
        _write_empty_course(self.courses_dir, "once-only")
        self.client.post("/admin/courses/once-only/quiz/create")

        response = self.client.post("/admin/courses/once-only/quiz/create")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Итоговый тест для этого курса уже создан.", response.text)

    def test_create_quiz_does_not_modify_course_or_lesson_files(self) -> None:
        _write_course(self.courses_dir, "stable-files")
        course_before = (
            self.courses_dir / "stable-files" / "course.json"
        ).read_text(encoding="utf-8")
        lesson_before = (
            self.courses_dir / "stable-files" / "lesson_01" / "lesson.json"
        ).read_text(encoding="utf-8")

        self.client.post("/admin/courses/stable-files/quiz/create")

        self.assertEqual(
            (self.courses_dir / "stable-files" / "course.json").read_text(encoding="utf-8"),
            course_before,
        )
        self.assertEqual(
            (
                self.courses_dir / "stable-files" / "lesson_01" / "lesson.json"
            ).read_text(encoding="utf-8"),
            lesson_before,
        )


if __name__ == "__main__":
    unittest.main()
