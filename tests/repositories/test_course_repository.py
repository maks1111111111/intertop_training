"""Tests for CourseRepository."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database.db import initialize_database
from app.repositories.course_repository import CourseRepository
from app.services.course_sync import sync_courses
from tests.web.test_web_ui import _write_course


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
