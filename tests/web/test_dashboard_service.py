"""Tests for the student dashboard service."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.content.runtime import ContentRuntime
from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories import quiz_repository
from app.repositories.progress_repository import ProgressRepository
from app.services.course_sync import sync_courses
from app.web.dashboard_service import CourseDashboardItem, DashboardService

TELEGRAM_ID = 1001


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


def _create_service(
    courses_dir: Path,
    *,
    telegram_id: int = TELEGRAM_ID,
) -> tuple[DashboardService, tempfile.TemporaryDirectory, Path, ProgressRepository]:
    db_tmp = tempfile.TemporaryDirectory()
    db_path = Path(db_tmp.name) / "test.db"
    initialize_database(db_path)
    sync_courses(courses_dir, db_path)
    upsert_telegram_user(
        db_path,
        telegram_id=telegram_id,
        username="learner",
        first_name="Test",
        last_name="User",
    )
    runtime = ContentRuntime(courses_dir)
    progress_repository = ProgressRepository()
    service = DashboardService(
        runtime,
        progress_repository,
        quiz_repository,
        db_path,
    )
    return service, db_tmp, db_path, progress_repository


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
    def _canonical_user_id(self, db_path: Path, telegram_id: int = TELEGRAM_ID) -> int:
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        return int(row["id"])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self._tmpdir.name) / "courses"
        self.courses_dir.mkdir()

    def tearDown(self) -> None:
        if hasattr(self, "_db_tmp"):
            self._db_tmp.cleanup()
        self._tmpdir.cleanup()

    def _make_service(
        self,
        *,
        telegram_id: int = TELEGRAM_ID,
    ) -> tuple[DashboardService, Path, ProgressRepository]:
        service, self._db_tmp, db_path, progress_repository = _create_service(
            self.courses_dir,
            telegram_id=telegram_id,
        )
        return service, db_path, progress_repository

    def test_get_courses_for_user_empty_runtime(self) -> None:
        db_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(db_tmp.cleanup)
        db_path = Path(db_tmp.name) / "test.db"
        initialize_database(db_path)
        courses_dir = Path(db_tmp.name) / "courses"
        courses_dir.mkdir()
        runtime = ContentRuntime(courses_dir)
        service = DashboardService(
            runtime,
            ProgressRepository(),
            quiz_repository,
            db_path,
        )

        items = service.get_courses_for_user(user_id=1)

        self.assertEqual(items, ())

    def test_get_courses_for_user_not_started_course(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        service, db_path, _ = self._make_service()
        user_id = self._canonical_user_id(db_path)

        items = service.get_courses_for_user(user_id=user_id)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.slug, "alpha")
        self.assertEqual(item.title, "Title alpha")
        self.assertEqual(item.description, "Description for alpha")
        self.assertEqual(item.status, "not_started")
        self.assertEqual(item.progress_percent, 0)
        self.assertIsNone(item.best_quiz_score)
        self.assertIsNone(item.last_quiz_score)
        self.assertEqual(item.last_lesson_title, "")
        self.assertEqual(item.continue_url, "/courses/alpha")

    def test_get_courses_for_user_returns_dashboard_items(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        service, db_path, _ = self._make_service()
        user_id = self._canonical_user_id(db_path)

        items = service.get_courses_for_user(user_id=user_id)

        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], CourseDashboardItem)

    def test_password_only_user_dashboard_does_not_require_telegram_id(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")

        db_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(db_tmp.cleanup)
        db_path = Path(db_tmp.name) / "test.db"
        initialize_database(db_path)
        sync_courses(self.courses_dir, db_path)

        with get_connection(db_path) as connection:
            user_id = int(
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
                    ("web-only", "Web", "Only"),
                ).lastrowid
            )

        service = DashboardService(
            ContentRuntime(self.courses_dir),
            ProgressRepository(),
            quiz_repository,
            db_path,
        )

        items = service.get_courses_for_user(user_id)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].slug, "alpha")
        self.assertEqual(items[0].status, "not_started")
        self.assertEqual(items[0].progress_percent, 0)

    def test_invalid_canonical_user_id_is_rejected(self) -> None:
        db_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(db_tmp.cleanup)
        db_path = Path(db_tmp.name) / "test.db"
        initialize_database(db_path)

        service = DashboardService(
            ContentRuntime(self.courses_dir),
            ProgressRepository(),
            quiz_repository,
            db_path,
        )

        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    service.get_courses_for_user(
                        invalid  # type: ignore[arg-type]
                    )


    def test_service_stores_dependencies(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        progress_repository = MagicMock(spec=ProgressRepository)
        quiz_repo = MagicMock()
        db_path = Path("/tmp/test.db")

        service = DashboardService(runtime, progress_repository, quiz_repo, db_path)

        self.assertIs(service._runtime, runtime)
        self.assertIs(service._progress_repository, progress_repository)
        self.assertIs(service._quiz_repository, quiz_repo)
        self.assertEqual(service._db_path, db_path)


class DashboardServiceIntegrationTests(unittest.TestCase):
    def _canonical_user_id(self, db_path: Path, telegram_id: int = TELEGRAM_ID) -> int:
        with get_connection(db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        return int(row["id"])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self._tmpdir.name) / "courses"
        self.courses_dir.mkdir()

    def tearDown(self) -> None:
        self._db_tmp.cleanup()
        self._tmpdir.cleanup()

    def _make_service(
        self,
        *,
        telegram_id: int = TELEGRAM_ID,
    ) -> tuple[DashboardService, Path, ProgressRepository]:
        service, self._db_tmp, db_path, progress_repository = _create_service(
            self.courses_dir,
            telegram_id=telegram_id,
        )
        return service, db_path, progress_repository

    def test_dashboard_reflects_repository_progress(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        service, db_path, progress_repository = self._make_service()

        progress_repository.start_course(db_path, TELEGRAM_ID, "alpha")
        progress_repository.complete_lesson(
            db_path,
            TELEGRAM_ID,
            "alpha",
            "lesson_01",
        )

        item = service.get_courses_for_user(self._canonical_user_id(db_path))[0]

        self.assertEqual(item.status, "in_progress")
        self.assertEqual(item.progress_percent, 33)
        self.assertEqual(item.last_lesson_title, "First lesson")
        self.assertEqual(item.continue_url, "/courses/alpha/lessons/lesson_02")

    def test_dashboard_reflects_quiz_statistics(self) -> None:
        _write_minimal_course(self.courses_dir, "alpha")
        service, db_path, _ = self._make_service()

        first_attempt_id = quiz_repository.create_attempt(
            db_path,
            telegram_id=TELEGRAM_ID,
            course_slug="alpha",
            quiz_version=1,
            questions_count=2,
        )
        self.assertIsNotNone(first_attempt_id)
        quiz_repository.save_answer(
            db_path,
            int(first_attempt_id),
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            db_path,
            int(first_attempt_id),
            question_id="q2",
            selected_option_id="a",
            is_correct=False,
        )
        quiz_repository.finish_attempt(db_path, int(first_attempt_id))

        second_attempt_id = quiz_repository.create_attempt(
            db_path,
            telegram_id=TELEGRAM_ID,
            course_slug="alpha",
            quiz_version=1,
            questions_count=2,
        )
        self.assertIsNotNone(second_attempt_id)
        quiz_repository.save_answer(
            db_path,
            int(second_attempt_id),
            question_id="q1",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.save_answer(
            db_path,
            int(second_attempt_id),
            question_id="q2",
            selected_option_id="a",
            is_correct=True,
        )
        quiz_repository.finish_attempt(db_path, int(second_attempt_id))

        item = service.get_courses_for_user(self._canonical_user_id(db_path))[0]

        self.assertEqual(item.best_quiz_score, 100.0)
        self.assertEqual(item.last_quiz_score, 100.0)

    def test_continue_url_changes_after_progress(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        service, db_path, progress_repository = self._make_service()

        before = service.get_courses_for_user(self._canonical_user_id(db_path))[0]
        self.assertEqual(before.continue_url, "/courses/alpha")

        progress_repository.start_course(db_path, TELEGRAM_ID, "alpha")
        after_start = service.get_courses_for_user(self._canonical_user_id(db_path))[0]
        self.assertEqual(after_start.continue_url, "/courses/alpha/lessons/lesson_01")

        progress_repository.complete_lesson(
            db_path,
            TELEGRAM_ID,
            "alpha",
            "lesson_01",
        )
        after_lesson = service.get_courses_for_user(self._canonical_user_id(db_path))[0]
        self.assertEqual(after_lesson.continue_url, "/courses/alpha/lessons/lesson_02")

    def test_completed_course_is_rendered_correctly(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        service, db_path, progress_repository = self._make_service()

        progress_repository.start_course(db_path, TELEGRAM_ID, "alpha")
        for lesson_slug in ("lesson_01", "lesson_02", "lesson_03"):
            progress_repository.complete_lesson(
                db_path,
                TELEGRAM_ID,
                "alpha",
                lesson_slug,
            )
        progress_repository.complete_course(db_path, TELEGRAM_ID, "alpha")

        item = service.get_courses_for_user(self._canonical_user_id(db_path))[0]

        self.assertEqual(item.status, "completed")
        self.assertEqual(item.progress_percent, 100)
        self.assertEqual(item.last_lesson_title, "Third lesson")
        self.assertEqual(item.continue_url, "/courses/alpha/lessons/lesson_03")


if __name__ == "__main__":
    unittest.main()
