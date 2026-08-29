"""Integration tests for learner Web practical-task pages."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import Request
from fastapi.testclient import TestClient

from app.ai.review_interfaces import ReviewFeedback, ReviewResult
from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories import practical_task_attempt_repository
from app.repositories.progress_repository import ProgressRepository
from app.web.progress_service import WebProgressService
from app.web.router import get_current_web_identity, require_web_management_identity
from app.web.web_identity_service import WebIdentity
from app.web.web_practical_task_service import WebPracticalTaskService
from tests.web.test_web_ui import (
    _WEB_TEST_TELEGRAM_ID,
    _authenticate_test_web_user,
    _create_test_app,
    _write_course,
)


def _write_course_with_structured_task(
    courses_dir: Path,
    slug: str = "task-course",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        '{"title": "Task Course", "status": "published", "language": "ru"}',
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps(
            {
                "title": "Practical lesson",
                "order": 1,
                "description": "Lesson body.",
                "structured_practical_task": {
                    "title": "Проверка рабочей зоны",
                    "description": "Осмотрите рабочую зону и опишите риски.",
                    "expected_result": "Все риски выявлены и описаны.",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class FakeReviewer:
    def __init__(self) -> None:
        self.calls = 0
        self.last_request = None

    def review(self, request):
        self.calls += 1
        self.last_request = request
        return ReviewResult(
            score=8,
            max_score=10,
            passed=True,
            feedback=ReviewFeedback(
                summary="Хороший ответ.",
                strengths=("Верная последовательность",),
                improvements=("Добавьте детали",),
            ),
        )


class WebPracticalTaskPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        _write_course_with_structured_task(self.courses_dir, "task-course")
        _write_course(self.courses_dir, "plain", title="Plain Course")

        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )
        self.user_id = _authenticate_test_web_user(self.app)
        self.client = TestClient(self.app)

        self.reviewer = FakeReviewer()
        self.app.state.web_practical_task_service = WebPracticalTaskService(
            self.app.state.content_runtime,
            self.reviewer,
            self.db_path,
        )

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _lesson_url(self, slug: str = "task-course") -> str:
        return f"/courses/{slug}/lessons/lesson_01"

    def _submit_url(self, slug: str = "task-course") -> str:
        return f"/courses/{slug}/lessons/lesson_01/practical-task"

    def test_authenticated_learner_sees_practical_task_form(self) -> None:
        response = self.client.get(self._lesson_url())

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Проверка рабочей зоны", html)
        self.assertIn("lesson-practical-task-form", html)
        self.assertIn('name="learner_answer"', html)
        self.assertIn("Отправить на проверку", html)
        self.assertIn("Ожидаемый результат", html)

    def test_lesson_without_structured_task_has_no_submission_form(self) -> None:
        response = self.client.get(self._lesson_url("plain"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("lesson-practical-task-form", response.text)
        self.assertNotIn("Отправить на проверку", response.text)

    def test_successful_post_creates_reviewed_attempt_for_canonical_user(self) -> None:
        response = self.client.post(
            self._submit_url(),
            data={"learner_answer": "  Я осмотрел рабочую зону.  "},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("attempt=", response.headers["location"])
        self.assertEqual(self.reviewer.calls, 1)

        attempts = (
            practical_task_attempt_repository.get_attempts_for_lesson_for_user(
                self.db_path,
                self.user_id,
                "task-course",
                "lesson_01",
            )
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].user_id, self.user_id)
        self.assertEqual(attempts[0].status, "reviewed")
        self.assertEqual(attempts[0].learner_answer, "Я осмотрел рабочую зону.")

    def test_web_only_user_with_null_telegram_id_can_submit(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "UPDATE users SET telegram_id = NULL WHERE id = ?",
                (self.user_id,),
            )

        response = self.client.post(
            self._submit_url(),
            data={"learner_answer": "Ответ без Telegram."},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        attempt = practical_task_attempt_repository.get_attempts_for_lesson_for_user(
            self.db_path,
            self.user_id,
            "task-course",
            "lesson_01",
        )[0]
        self.assertIsNone(attempt.telegram_id)

    def test_successful_review_is_rendered(self) -> None:
        submit = self.client.post(
            self._submit_url(),
            data={"learner_answer": "Подробный ответ."},
            follow_redirects=True,
        )

        html = submit.text
        self.assertIn("Результат проверки", html)
        self.assertIn("8 / 10", html)
        self.assertIn("Задание принято", html)
        self.assertIn("Хороший ответ.", html)
        self.assertIn("Верная последовательность", html)
        self.assertIn("Добавьте детали", html)

    def test_empty_answer_shows_validation_error_without_ai_call(self) -> None:
        response = self.client.post(
            self._submit_url(),
            data={"learner_answer": "   "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Введите ответ на практическое задание.", response.text)
        self.assertEqual(self.reviewer.calls, 0)
        attempts = practical_task_attempt_repository.get_attempts_for_lesson_for_user(
            self.db_path,
            self.user_id,
            "task-course",
            "lesson_01",
        )
        self.assertEqual(attempts, [])

    def test_unavailable_ai_review_shows_friendly_notice(self) -> None:
        self.app.state.web_practical_task_service = WebPracticalTaskService(
            self.app.state.content_runtime,
            None,
            self.db_path,
        )

        response = self.client.post(
            self._submit_url(),
            data={"learner_answer": "Ответ."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "AI-проверка практических заданий сейчас недоступна.",
            response.text,
        )

    def test_unknown_course_or_lesson_returns_404(self) -> None:
        missing_course = self.client.post(
            "/courses/missing/lessons/lesson_01/practical-task",
            data={"learner_answer": "Ответ."},
        )
        self.assertEqual(missing_course.status_code, 404)

        missing_lesson = self.client.post(
            "/courses/task-course/lessons/missing/practical-task",
            data={"learner_answer": "Ответ."},
        )
        self.assertEqual(missing_lesson.status_code, 404)

    def test_anonymous_post_is_blocked(self) -> None:
        self.app.dependency_overrides.pop(get_current_web_identity, None)

        response = self.client.post(
            self._submit_url(),
            data={"learner_answer": "Ответ."},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/login")

    def test_user_cannot_view_another_users_attempt_via_query_param(self) -> None:
        submit = self.client.post(
            self._submit_url(),
            data={"learner_answer": "Ответ первого пользователя."},
            follow_redirects=False,
        )
        attempt_id = practical_task_attempt_repository.get_attempts_for_lesson_for_user(
            self.db_path,
            self.user_id,
            "task-course",
            "lesson_01",
        )[0].id

        other_identity = WebIdentity(
            user_id=999,
            telegram_id=None,
            company_id="intertop",
            company_name="Intertop Retail",
            role="student",
        )

        def provide_other_identity(request: Request) -> WebIdentity:
            request.state.web_identity = other_identity
            return other_identity

        self.app.dependency_overrides[get_current_web_identity] = (
            provide_other_identity
        )

        response = self.client.get(
            f"{self._lesson_url()}?attempt={attempt_id}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Результат проверки", response.text)
        self.assertNotIn("Ответ первого пользователя.", response.text)

    def test_admin_preview_does_not_show_submission_form(self) -> None:
        management_user = WebIdentity(
            user_id=10,
            telegram_id=None,
            company_id="intertop",
            company_name="Intertop Retail",
            role="admin",
        )

        def provide_management_identity(request: Request) -> WebIdentity:
            request.state.web_identity = management_user
            return management_user

        self.app.dependency_overrides[get_current_web_identity] = (
            provide_management_identity
        )
        self.app.dependency_overrides[require_web_management_identity] = (
            provide_management_identity
        )

        response = self.client.get(
            "/admin/courses/task-course/preview/lessons/lesson_01",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Проверка рабочей зоны", response.text)
        self.assertNotIn("lesson-practical-task-form", response.text)
        self.assertNotIn("Отправить на проверку", response.text)

        attempts = practical_task_attempt_repository.get_attempts_for_lesson_for_user(
            self.db_path,
            self.user_id,
            "task-course",
            "lesson_01",
        )
        self.assertEqual(attempts, [])

    def test_lesson_progress_behavior_remains_intact(self) -> None:
        progress = WebProgressService(
            self.db_path,
            ProgressRepository(),
            self.user_id,
        )
        self.assertFalse(
            progress.is_lesson_completed("task-course", "lesson_01")
        )

        response = self.client.get(self._lesson_url())
        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            progress.is_lesson_completed("task-course", "lesson_01")
        )

    def test_ai_failure_after_pending_attempt_shows_friendly_notice(self) -> None:
        reviewer = MagicMock()
        reviewer.review.side_effect = RuntimeError("provider failed")
        self.app.state.web_practical_task_service = WebPracticalTaskService(
            self.app.state.content_runtime,
            reviewer,
            self.db_path,
        )

        response = self.client.post(
            self._submit_url(),
            data={"learner_answer": "Ответ."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось завершить проверку ответа.", response.text)
        attempts = practical_task_attempt_repository.get_attempts_for_lesson_for_user(
            self.db_path,
            self.user_id,
            "task-course",
            "lesson_01",
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, "pending")


if __name__ == "__main__":
    unittest.main()
