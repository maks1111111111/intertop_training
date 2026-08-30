"""Tests for the student dashboard Web page."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.database.db import get_connection, upsert_telegram_user
from app.repositories import quiz_repository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app

WEB_DASHBOARD_TELEGRAM_ID = 1


def _write_minimal_course(courses_dir: Path, slug: str) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "description": f"Description for {slug}",
                "status": "published",
                "order": 1,
            }
        ),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "First lesson", "order": 1}),
        encoding="utf-8",
    )


def _write_multi_lesson_course(courses_dir: Path, slug: str = "alpha") -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "description": f"Description for {slug}",
                "status": "published",
                "order": 1,
            }
        ),
        encoding="utf-8",
    )
    for lesson_slug, title, order in (
        ("lesson_01", "First lesson", 1),
        ("lesson_02", "Second lesson", 2),
        ("lesson_03", "Third lesson", 3),
    ):
        lesson_dir = course_dir / lesson_slug
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            json.dumps({"title": title, "order": order}),
            encoding="utf-8",
        )


def _authenticate_dashboard_user(app) -> int:
    """Provide an authenticated canonical Web identity for dashboard tests."""
    upsert_telegram_user(
        app.state.db_path,
        telegram_id=WEB_DASHBOARD_TELEGRAM_ID,
        username="web-learner",
        first_name="Web",
        last_name="Learner",
    )
    with get_connection(app.state.db_path) as connection:
        row = connection.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (WEB_DASHBOARD_TELEGRAM_ID,),
        ).fetchone()

    assert row is not None
    user_id = int(row["id"])

    identity = WebIdentity(
        user_id=user_id,
        telegram_id=WEB_DASHBOARD_TELEGRAM_ID,
        company_id="intertop",
        company_name="Intertop Retail",
        role="student",
    )
    def provide_identity(request: Request) -> WebIdentity:
        request.state.web_identity = identity
        return identity

    app.dependency_overrides[get_current_web_identity] = provide_identity
    return user_id


def _prepare_dashboard_db(app, courses_dir: Path) -> ProgressRepository:
    sync_courses(courses_dir, app.state.db_path)
    upsert_telegram_user(
        app.state.db_path,
        telegram_id=WEB_DASHBOARD_TELEGRAM_ID,
        username="web-learner",
        first_name="Web",
        last_name="Learner",
    )
    return ProgressRepository()


class DashboardPageTests(unittest.TestCase):
    """Verify GET /dashboard rendering and wiring."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)
        _authenticate_dashboard_user(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_dashboard_returns_200(self) -> None:
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)

    def test_dashboard_contains_page_title(self) -> None:
        response = self.client.get("/dashboard")

        self.assertIn("Моё обучение", response.text)

    def test_dashboard_empty_state(self) -> None:
        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("Доступных курсов пока нет", html)

    def test_dashboard_renders_course_title(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn("Title alpha", response.text)

    def test_dashboard_renders_progress(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("0%", html)
        self.assertIn("dashboard-progress-bar", html)

    def test_dashboard_renders_continue_url_for_not_started_course(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn('href="/courses/alpha"', response.text)
        self.assertIn("Начать курс", response.text)

    def test_dashboard_nav_link_is_active(self) -> None:
        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn('href="/dashboard"', html)
        self.assertIn("Моё обучение", html)
        self.assertIn("is-active", html)

    def test_dashboard_uses_app_state_runtime(self) -> None:
        _write_minimal_course(self.courses_dir, "beta")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)

        response = self.client.get("/dashboard")

        self.assertIn("Title beta", response.text)
        self.assertNotIn("Title alpha", response.text)


class DashboardPageIntegrationTests(unittest.TestCase):
    """Verify dashboard page reflects repository-backed progress and quiz data."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)
        self.progress_repository = ProgressRepository()
        _authenticate_dashboard_user(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_dashboard_reflects_repository_progress(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        self.progress_repository.start_course(
            self.db_path,
            WEB_DASHBOARD_TELEGRAM_ID,
            "alpha",
        )
        self.progress_repository.complete_lesson(
            self.db_path,
            WEB_DASHBOARD_TELEGRAM_ID,
            "alpha",
            "lesson_01",
        )

        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("33%", html)
        self.assertIn("В процессе", html)
        self.assertIn("Последний урок: First lesson", html)
        self.assertIn('href="/courses/alpha/lessons/lesson_02"', html)
        self.assertIn("Продолжить", html)

    def test_dashboard_reflects_quiz_statistics(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        attempt_id = quiz_repository.create_attempt(
            self.db_path,
            telegram_id=WEB_DASHBOARD_TELEGRAM_ID,
            course_slug="alpha",
            quiz_version=1,
            questions_count=2,
        )
        self.assertIsNotNone(attempt_id)
        quiz_repository.save_answer(
            self.db_path,
            int(attempt_id),
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            self.db_path,
            int(attempt_id),
            question_id="q2",
            selected_option_id="a",
            is_correct=False,
        )
        quiz_repository.finish_attempt(self.db_path, int(attempt_id))

        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("Лучший результат теста", html)
        self.assertIn("50.0%", html)
        self.assertIn("Последний результат теста", html)

    def test_continue_url_changes_after_progress(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        before = self.client.get("/dashboard")
        self.assertIn('href="/courses/alpha"', before.text)
        self.assertIn("Начать курс", before.text)

        self.progress_repository.start_course(
            self.db_path,
            WEB_DASHBOARD_TELEGRAM_ID,
            "alpha",
        )
        after_start = self.client.get("/dashboard")
        self.assertIn(
            'href="/courses/alpha/lessons/lesson_01"',
            after_start.text,
        )
        self.assertIn("Продолжить", after_start.text)

        self.progress_repository.complete_lesson(
            self.db_path,
            WEB_DASHBOARD_TELEGRAM_ID,
            "alpha",
            "lesson_01",
        )
        after_lesson = self.client.get("/dashboard")
        self.assertIn(
            'href="/courses/alpha/lessons/lesson_02"',
            after_lesson.text,
        )

    def test_completed_course_is_rendered_correctly(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        self.progress_repository.start_course(
            self.db_path,
            WEB_DASHBOARD_TELEGRAM_ID,
            "alpha",
        )
        for lesson_slug in ("lesson_01", "lesson_02", "lesson_03"):
            self.progress_repository.complete_lesson(
                self.db_path,
                WEB_DASHBOARD_TELEGRAM_ID,
                "alpha",
                lesson_slug,
            )
        self.progress_repository.complete_course(
            self.db_path,
            WEB_DASHBOARD_TELEGRAM_ID,
            "alpha",
        )

        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("100%", html)
        self.assertIn("Завершён", html)
        self.assertIn("Последний урок: Third lesson", html)
        self.assertIn('href="/courses/alpha/lessons/lesson_03"', html)
        self.assertIn("Продолжить", html)

    def test_assigned_course_renders_assigned_badge_and_start_cta(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (WEB_DASHBOARD_TELEGRAM_ID,),
            ).fetchone()
        assert row is not None
        user_id = int(row["id"])

        assigned = self.progress_repository.assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )
        self.assertTrue(assigned)

        response = self.client.get("/dashboard")
        html = response.text

        self.assertIn("Назначен", html)
        self.assertIn("0%", html)
        self.assertIn("Начать курс", html)
        self.assertIn('href="/courses/alpha"', html)
        self.assertNotIn('href="/courses/alpha/lessons/', html)

    def test_assigned_course_does_not_show_raw_status_label(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (WEB_DASHBOARD_TELEGRAM_ID,),
            ).fetchone()
        assert row is not None
        user_id = int(row["id"])

        self.progress_repository.assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )

        response = self.client.get("/dashboard")
        html = response.text

        badge_start = html.find("dashboard-status-badge")
        self.assertNotEqual(badge_start, -1)
        badge_section = html[badge_start : badge_start + 200]
        self.assertIn("Назначен", badge_section)
        self.assertNotIn(">assigned<", badge_section)

    def test_starting_assigned_course_updates_dashboard_display(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        _prepare_dashboard_db(self.app, self.courses_dir)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (WEB_DASHBOARD_TELEGRAM_ID,),
            ).fetchone()
        assert row is not None
        user_id = int(row["id"])

        self.progress_repository.assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )

        assigned_response = self.client.get("/dashboard")
        self.assertIn("Назначен", assigned_response.text)
        self.assertIn("Начать курс", assigned_response.text)

        self.progress_repository.start_course_for_user(
            self.db_path,
            user_id,
            "alpha",
        )

        started_response = self.client.get("/dashboard")
        html = started_response.text

        self.assertIn("В процессе", html)
        self.assertIn("Продолжить", html)
        self.assertIn('href="/courses/alpha/lessons/lesson_01"', html)


if __name__ == "__main__":
    unittest.main()
