"""Tests for the student dashboard service foundation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.content.runtime import ContentRuntime
from app.repositories import quiz_repository
from app.repositories.progress_repository import ProgressRepository
from app.web.dashboard_service import CourseDashboardItem, DashboardService


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


class CourseDashboardItemTests(unittest.TestCase):
    def test_dataclass_creation(self) -> None:
        item = CourseDashboardItem(
            slug="alpha",
            title="Alpha course",
            description="Course description",
            status="in_progress",
            progress_percent=40,
            best_quiz_score=80.0,
            last_quiz_score=60.0,
            last_lesson_title="Lesson one",
            continue_url="/courses/alpha/lessons/lesson_01",
        )

        self.assertEqual(item.slug, "alpha")
        self.assertEqual(item.title, "Alpha course")
        self.assertEqual(item.description, "Course description")
        self.assertEqual(item.status, "in_progress")
        self.assertEqual(item.progress_percent, 40)
        self.assertEqual(item.best_quiz_score, 80.0)
        self.assertEqual(item.last_quiz_score, 60.0)
        self.assertEqual(item.last_lesson_title, "Lesson one")
        self.assertEqual(item.continue_url, "/courses/alpha/lessons/lesson_01")


class DashboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self._tmpdir.name) / "courses"
        self.courses_dir.mkdir()
        self.runtime = ContentRuntime(self.courses_dir)
        self.progress_repository = ProgressRepository()
        self.service = DashboardService(
            self.runtime,
            self.progress_repository,
            quiz_repository,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_get_courses_for_user_empty_runtime(self) -> None:
        items = self.service.get_courses_for_user(telegram_id=12345)

        self.assertEqual(items, ())

    def test_get_courses_for_user_one_course(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.runtime.refresh()

        items = self.service.get_courses_for_user(telegram_id=12345)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.slug, "alpha")
        self.assertEqual(item.title, "Title alpha")
        self.assertEqual(item.description, "Description for alpha")
        self.assertEqual(item.status, "not_started")
        self.assertEqual(item.progress_percent, 0)
        self.assertIsNone(item.best_quiz_score)
        self.assertIsNone(item.last_quiz_score)
        self.assertEqual(item.last_lesson_title, "First lesson")
        self.assertEqual(item.continue_url, "/courses/alpha/lessons/lesson_01")

    def test_get_courses_for_user_returns_dashboard_items(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        self.runtime.refresh()

        items = self.service.get_courses_for_user(telegram_id=999)

        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], CourseDashboardItem)

    def test_service_stores_dependencies(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        progress_repository = MagicMock(spec=ProgressRepository)
        quiz_repository = MagicMock()

        service = DashboardService(runtime, progress_repository, quiz_repository)

        self.assertIs(service._runtime, runtime)
        self.assertIs(service._progress_repository, progress_repository)
        self.assertIs(service._quiz_repository, quiz_repository)

