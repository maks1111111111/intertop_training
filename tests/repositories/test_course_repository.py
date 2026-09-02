"""Tests for CourseRepository."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import initialize_database
from app.repositories.course_repository import CourseRepository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from tests.web.test_web_ui import _write_course


class CourseRepositoryLifecycleTests(unittest.TestCase):
    """Verify course repository lifecycle status helpers."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.db_tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.db_tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = CourseRepository()

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _sync(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        sync_courses(self.courses_dir, self.db_path)

    def test_set_status_published_to_archived(self) -> None:
        self._sync()

        updated = self.repository.set_status(self.db_path, "alpha", "archived")

        self.assertTrue(updated)
        row = self.repository.get_by_slug(self.db_path, "alpha")
        assert row is not None
        self.assertEqual(row["status"], "archived")

    def test_set_status_archived_to_published(self) -> None:
        self._sync()
        self.repository.set_status(self.db_path, "alpha", "archived")

        updated = self.repository.set_status(self.db_path, "alpha", "published")

        self.assertTrue(updated)
        row = self.repository.get_by_slug(self.db_path, "alpha")
        assert row is not None
        self.assertEqual(row["status"], "published")

    def test_set_status_returns_false_for_missing_slug(self) -> None:
        updated = self.repository.set_status(self.db_path, "missing", "archived")

        self.assertFalse(updated)

    def test_set_status_rejects_invalid_status(self) -> None:
        self._sync()

        with self.assertRaises(ValueError):
            self.repository.set_status(self.db_path, "alpha", "draft")

    def test_set_status_does_not_touch_unrelated_course(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        _write_course(self.courses_dir, "beta", title="Beta Course")
        sync_courses(self.courses_dir, self.db_path)

        self.repository.set_status(self.db_path, "alpha", "archived")

        beta = self.repository.get_by_slug(self.db_path, "beta")
        assert beta is not None
        self.assertEqual(beta["status"], "published")

    def test_count_active_enrollments_includes_assigned_and_in_progress(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        _write_course(self.courses_dir, "beta", title="Beta Course")
        sync_courses(self.courses_dir, self.db_path)
        user_id = self._create_user()
        progress = ProgressRepository()
        progress.assign_course_to_user(self.db_path, user_id, "alpha")
        progress.start_course_for_user(self.db_path, user_id, "beta")

        assigned_count = self.repository.count_active_enrollments(
            self.db_path,
            "alpha",
        )
        in_progress_count = self.repository.count_active_enrollments(
            self.db_path,
            "beta",
        )

        self.assertEqual(assigned_count, 1)
        self.assertEqual(in_progress_count, 1)

    def test_count_active_enrollments_excludes_completed(self) -> None:
        self._sync()
        user_id = self._create_user()
        progress = ProgressRepository()
        progress.start_course_for_user(self.db_path, user_id, "alpha")
        progress.complete_course_for_user(self.db_path, user_id, "alpha")

        count = self.repository.count_active_enrollments(self.db_path, "alpha")

        self.assertEqual(count, 0)

    def _create_user(self) -> int:
        from app.database.db import get_connection

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


class CourseRepositoryDeleteTests(unittest.TestCase):
    """Verify course repository delete behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.db_tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.db_tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.repository = CourseRepository()

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_delete_by_slug_removes_requested_course_only(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        _write_course(self.courses_dir, "beta", title="Beta Course")
        sync_courses(self.courses_dir, self.db_path)

        deleted = self.repository.delete_by_slug(self.db_path, "alpha")

        self.assertTrue(deleted)
        self.assertIsNone(self.repository.get_by_slug(self.db_path, "alpha"))
        self.assertIsNotNone(self.repository.get_by_slug(self.db_path, "beta"))

    def test_delete_by_slug_returns_false_for_missing_course(self) -> None:
        deleted = self.repository.delete_by_slug(self.db_path, "missing")

        self.assertFalse(deleted)


if __name__ == "__main__":
    unittest.main()
