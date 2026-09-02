"""HTTP tests for admin course archive and restore routes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.repositories.course_repository import CourseRepository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from app.web.manager_course_assignment_service import ManagerCourseAssignmentService
from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity
from tests.web.test_manager_course_assignment_service import (
    FakeTeamService,
    _member,
)
from tests.web.test_web_ui import (
    _authenticate_test_web_user,
    _create_test_app,
    _write_course,
)


def _management_identity(role: str = "admin") -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


def _write_archived_course(
    courses_dir: Path,
    slug: str = "archived",
    *,
    title: str = "Archived Course",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": title,
                "description": "Archived course description.",
                "status": "archived",
                "language": "ru",
            }
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        '{"title": "First lesson", "order": 1, "description": "Body text."}',
        encoding="utf-8",
    )


class AdminCourseLifecyclePageTests(unittest.TestCase):
    """Verify archive/restore admin routes and learner/manager behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _set_identity(self, role: str) -> None:
        self.app.dependency_overrides[get_current_web_identity] = lambda: _management_identity(
            role
        )

    def _sync_runtime(self) -> None:
        sync_courses(self.courses_dir, self.db_path)
        self.app.state.content_runtime.refresh()

    def test_archive_confirmation_page_for_publishable_course(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha/archive")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Архивирование курса", html)
        self.assertIn("Alpha Course", html)
        self.assertIn("Архивировать курс", html)

    def test_detail_page_links_to_archive_for_published_course(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha")

        self.assertIn("Архивировать курс", response.text)
        self.assertIn('href="/admin/courses/alpha/archive"', response.text)

    def test_post_archive_redirects_to_detail_and_hides_from_runtime(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.post(
            "/admin/courses/alpha/archive",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/courses/alpha")
        self.app.state.content_runtime.refresh()
        self.assertIsNone(self.app.state.content_runtime.get_course("alpha"))
        row = CourseRepository().get_by_slug(self.db_path, "alpha")
        assert row is not None
        self.assertEqual(row["status"], "archived")

    def test_active_assignment_blocks_archive_submit(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()
        user_id = _authenticate_test_web_user(self.app)
        self._set_identity("admin")
        ProgressRepository().assign_course_to_user(self.db_path, user_id, "alpha")

        response = self.client.post("/admin/courses/alpha/archive")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Курс нельзя архивировать, пока есть активные назначения.",
            response.text,
        )

    def test_admin_dashboard_shows_archived_course_without_open_link(self) -> None:
        self._set_identity("admin")
        _write_course(self.courses_dir, "alpha", title="Published Course")
        _write_archived_course(self.courses_dir, "archived", title="Archived Course")
        self._sync_runtime()
        CourseRepository().set_status(self.db_path, "archived", "archived")

        response = self.client.get("/admin")

        html = response.text
        self.assertIn("Published Course", html)
        self.assertIn("Archived Course", html)
        self.assertIn("Архив", html)
        self.assertIn('href="/courses/alpha"', html)
        self.assertNotIn('href="/courses/archived"', html)

    def test_archived_detail_shows_restore_without_preview(self) -> None:
        self._set_identity("admin")
        _write_archived_course(self.courses_dir, "archived", title="Archived Course")
        CourseRepository().save(
            self.db_path,
            "archived",
            "Archived Course",
            None,
            0,
        )
        CourseRepository().set_status(self.db_path, "archived", "archived")

        response = self.client.get("/admin/courses/archived")

        html = response.text
        self.assertIn("Восстановить курс", html)
        self.assertIn("Архив", html)
        self.assertNotIn("Предпросмотр курса", html)
        self.assertNotIn("Редактировать", html)

    def test_post_restore_returns_course_to_runtime(self) -> None:
        self._set_identity("admin")
        _write_archived_course(self.courses_dir, "archived", title="Archived Course")
        CourseRepository().save(
            self.db_path,
            "archived",
            "Archived Course",
            None,
            0,
        )
        CourseRepository().set_status(self.db_path, "archived", "archived")

        response = self.client.post(
            "/admin/courses/archived/restore",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.app.state.content_runtime.refresh()
        self.assertIsNotNone(self.app.state.content_runtime.get_course("archived"))

    def test_learner_catalog_hides_archived_course(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        _write_archived_course(self.courses_dir, "archived", title="Archived Course")
        self._sync_runtime()
        CourseRepository().set_status(self.db_path, "archived", "archived")
        _authenticate_test_web_user(self.app)

        response = self.client.get("/courses")

        html = response.text
        self.assertIn("Alpha Course", html)
        self.assertNotIn("Archived Course", html)

    def test_manager_cannot_assign_archived_course(self) -> None:
        _write_archived_course(self.courses_dir, "archived", title="Archived Course")
        CourseRepository().save(
            self.db_path,
            "archived",
            "Archived Course",
            None,
            0,
        )
        CourseRepository().set_status(self.db_path, "archived", "archived")
        self.app.state.content_runtime.refresh()

        member = _member(user_id=2)

        assignment_service = ManagerCourseAssignmentService(
            team_service=FakeTeamService(member=member),
            progress_repository=ProgressRepository(),
            runtime=self.app.state.content_runtime,
            db_path=self.db_path,
        )
        result = assignment_service.assign_course(
            "intertop",
            2,
            "archived",
            assigned_by_user_id=10,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.code, "course_not_found")

    def test_student_cannot_access_archive_confirmation(self) -> None:
        self._set_identity("student")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._sync_runtime()

        response = self.client.get("/admin/courses/alpha/archive")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
