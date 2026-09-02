"""Tests for AdminCourseDeleteService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content.runtime import ContentRuntime
from app.database.db import get_connection, initialize_database
from app.repositories.course_repository import CourseRepository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from app.web.admin_course_delete_service import (
    AdminCourseDeleteError,
    AdminCourseDeleteService,
)
from tests.web.test_web_ui import _write_course


class AdminCourseDeleteServiceTests(unittest.TestCase):
    """Unit tests for safe permanent course deletion."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.db_tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.db_tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminCourseDeleteService(
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

    def test_unused_course_can_be_deleted(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        result = self.service.delete_course("alpha")

        self.assertTrue(result.success)
        self.assertEqual(result.code, "deleted")
        self.assertFalse((self.courses_dir / "alpha").exists())
        self.assertIsNone(
            CourseRepository().get_by_slug(self.db_path, "alpha"),
        )
        self.runtime.refresh()
        self.assertIsNone(self.runtime.get_course("alpha"))

    def test_directory_removed_and_course_disappears_after_refresh(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        self.assertIsNotNone(self.runtime.get_course("alpha"))

        self.service.delete_course("alpha")
        self.runtime.refresh()

        self.assertFalse((self.courses_dir / "alpha").exists())
        self.assertIsNone(self.runtime.get_course("alpha"))
        self.assertIsNone(
            CourseRepository().get_by_slug(self.db_path, "alpha"),
        )

    def test_unknown_course_returns_not_found(self) -> None:
        result = self.service.delete_course("missing-course")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "not_found")

    def test_traversal_slug_rejected(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        with self.assertRaises(AdminCourseDeleteError):
            self.service.get_delete_view("../alpha")

        with self.assertRaises(AdminCourseDeleteError):
            self.service.delete_course("../alpha")

    def test_enrollment_blocks_delete(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )

        view = self.service.get_delete_view("alpha")
        assert view is not None
        self.assertFalse(view.can_delete)
        self.assertEqual(view.history.enrollments_count, 1)

        result = self.service.delete_course("alpha")
        self.assertFalse(result.success)
        self.assertEqual(result.code, "course_has_history")
        self.assertTrue((self.courses_dir / "alpha").exists())

    def test_quiz_attempt_blocks_delete(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO quiz_attempts (
                    user_id,
                    course_slug,
                    quiz_version,
                    started_at,
                    questions_count
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (user_id, "alpha", 1, 1),
            )

        view = self.service.get_delete_view("alpha")
        assert view is not None
        self.assertFalse(view.can_delete)
        self.assertEqual(view.history.quiz_attempts_count, 1)

    def test_practical_attempt_blocks_delete(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO practical_task_attempts (
                    user_id,
                    course_slug,
                    lesson_slug,
                    task_title,
                    task_description,
                    expected_result,
                    learner_answer,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "alpha",
                    "lesson_01",
                    "Task",
                    "Description",
                    "Expected",
                    "Answer",
                    "pending",
                ),
            )

        view = self.service.get_delete_view("alpha")
        assert view is not None
        self.assertFalse(view.can_delete)
        self.assertEqual(view.history.practical_task_attempts_count, 1)

    def test_web_lesson_progress_blocks_delete(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO web_lesson_progress (
                    user_id,
                    course_slug,
                    lesson_id
                )
                VALUES (?, ?, ?)
                """,
                (str(user_id), "alpha", "lesson_01"),
            )

        view = self.service.get_delete_view("alpha")
        assert view is not None
        self.assertFalse(view.can_delete)
        self.assertEqual(view.history.web_lesson_progress_count, 1)

    def test_multiple_history_types_reported(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()
        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO quiz_attempts (
                    user_id,
                    course_slug,
                    quiz_version,
                    started_at,
                    questions_count
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (user_id, "alpha", 1, 1),
            )

        view = self.service.get_delete_view("alpha")
        assert view is not None
        self.assertEqual(view.history.enrollments_count, 1)
        self.assertEqual(view.history.quiz_attempts_count, 1)
        self.assertGreater(view.history.total, 0)

    @patch("app.web.admin_course_delete_service.shutil.rmtree")
    def test_filesystem_failure_is_controlled(self, mock_rmtree) -> None:
        mock_rmtree.side_effect = OSError("permission denied")
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        result = self.service.delete_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "filesystem_delete_failure")
        self.assertTrue((self.courses_dir / "alpha").exists())
        self.assertIsNotNone(
            CourseRepository().get_by_slug(self.db_path, "alpha"),
        )

    @patch.object(CourseRepository, "delete_by_slug", side_effect=RuntimeError("db"))
    def test_finalize_failure_is_controlled_and_preserves_db_row(
        self,
        _mock_delete,
    ) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        result = self.service.delete_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "delete_finalize_failure")
        self.assertFalse((self.courses_dir / "alpha").exists())
        self.assertIsNotNone(
            CourseRepository().get_by_slug(self.db_path, "alpha"),
        )

    @patch(
        "app.web.admin_course_delete_service.RuntimeRefreshService.refresh",
        side_effect=RuntimeError("refresh"),
    )
    def test_runtime_refresh_failure_is_controlled(
        self,
        _mock_refresh,
    ) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        result = self.service.delete_course("alpha")

        self.assertFalse(result.success)
        self.assertEqual(result.code, "delete_finalize_failure")
        self.assertFalse((self.courses_dir / "alpha").exists())
        self.assertIsNone(
            CourseRepository().get_by_slug(self.db_path, "alpha"),
        )

    def test_post_recheck_blocks_when_history_appears(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self._refresh()

        view_before = self.service.get_delete_view("alpha")
        assert view_before is not None
        self.assertTrue(view_before.can_delete)

        user_id = self._create_user()
        ProgressRepository().assign_course_to_user(
            self.db_path,
            user_id,
            "alpha",
        )

        result = self.service.delete_course("alpha")
        self.assertEqual(result.code, "course_has_history")
        self.assertTrue((self.courses_dir / "alpha").exists())


if __name__ == "__main__":
    unittest.main()
