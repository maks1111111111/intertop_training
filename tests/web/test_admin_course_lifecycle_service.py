"""Tests for AdminCourseLifecycleService."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content.runtime import ContentRuntime
from app.content.runtime_loader import get_course
from app.database.db import get_connection, initialize_database
from app.repositories.course_repository import CourseRepository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from app.web.admin_course_lifecycle_service import AdminCourseLifecycleService
from tests.web.test_web_ui import _write_course


class AdminCourseLifecycleServiceTests(unittest.TestCase):
    """Unit tests for archive and restore lifecycle."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.db_tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.db_tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminCourseLifecycleService(
            self.courses_dir,
            self.runtime,
            self.db_path,
        )

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _refresh(self) -> None:
        sync_courses(self.courses_dir, self.db_path)
        self.runtime.refresh()

    def _create_user(self) -> int:
        with get_connection(self.db_path) as connection:
            return int(
                connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        first_name,
                        last_name
                    )
                    VALUES (NULL, ?, ?, ?)
                    """,
                    ("web-only", "Web", "Learner"),
                ).lastrowid
            )

    def test_archive_course_without_active_assignments(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        result = self.service.archive_course("alpha")

        self.assertTrue(result.success)
        self.assertEqual(result.code, "archived")
        archived = get_course(self.courses_dir, "alpha")
        assert archived is not None
        self.assertEqual(archived.status, "archived")
        self.runtime.refresh()
        self.assertIsNone(self.runtime.get_course("alpha"))
        row = CourseRepository().get_by_slug(self.db_path, "alpha")
        assert row is not None
        self.assertEqual(row["status"], "archived")

    def test_restore_course_returns_to_published(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        self.service.archive_course("alpha")

        result = self.service.restore_course("alpha")

        self.assertTrue(result.success)
        self.assertEqual(result.code, "restored")
        restored = get_course(self.courses_dir, "alpha")
        assert restored is not None
        self.assertEqual(restored.status, "published")
        self.runtime.refresh()
        self.assertIsNotNone(self.runtime.get_course("alpha"))
        row = CourseRepository().get_by_slug(self.db_path, "alpha")
        assert row is not None
        self.assertEqual(row["status"], "published")

    def test_archive_blocked_by_active_assigned_enrollment(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(self.db_path, user_id, "alpha")

        result = self.service.archive_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "active_assignments")
        course = get_course(self.courses_dir, "alpha")
        assert course is not None
        self.assertEqual(course.status, "published")

    def test_archive_allowed_when_only_completed_enrollment_exists(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        progress = ProgressRepository()
        progress.start_course_for_user(self.db_path, user_id, "alpha")
        progress.complete_course_for_user(self.db_path, user_id, "alpha")

        result = self.service.archive_course("alpha")

        self.assertTrue(result.success)
        self.assertEqual(result.code, "archived")

    def test_archive_view_reports_active_assignment_count(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(self.db_path, user_id, "alpha")

        view = self.service.get_archive_view("alpha")

        assert view is not None
        self.assertEqual(view.active_assignments_count, 1)
        self.assertFalse(view.can_archive)

    def test_archive_not_found(self) -> None:
        result = self.service.archive_course("missing")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "not_found")

    def test_restore_already_published(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        result = self.service.restore_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "already_published")

    def test_archive_already_archived(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        self.service.archive_course("alpha")

        result = self.service.archive_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "already_archived")

    def test_filesystem_write_failure_leaves_db_published(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        with patch(
            "app.web.admin_course_lifecycle_service._atomic_write_json",
            side_effect=OSError("disk full"),
        ):
            result = self.service.archive_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "filesystem_write_failure")
        row = CourseRepository().get_by_slug(self.db_path, "alpha")
        assert row is not None
        self.assertEqual(row["status"], "published")

    def test_database_update_failure_rolls_back_filesystem(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        with patch.object(
            CourseRepository,
            "set_status",
            return_value=False,
        ):
            result = self.service.archive_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "database_update_failure")
        course = get_course(self.courses_dir, "alpha")
        assert course is not None
        self.assertEqual(course.status, "published")

    def test_history_rows_remain_after_archive(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        progress = ProgressRepository()
        progress.start_course_for_user(self.db_path, user_id, "alpha")
        progress.complete_course_for_user(self.db_path, user_id, "alpha")

        self.service.archive_course("alpha")

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM enrollments
                INNER JOIN courses ON courses.id = enrollments.course_id
                WHERE courses.slug = ?
                """,
                ("alpha",),
            ).fetchone()
        self.assertEqual(int(count["count"]), 1)


if __name__ == "__main__":
    unittest.main()
