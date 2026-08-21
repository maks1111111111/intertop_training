from types import SimpleNamespace
import unittest
from pathlib import Path

from app.web.manager_employee_analytics_service import (
    ManagerEmployeeAnalyticsService,
)


class FakeRuntime:
    def get_courses(self):
        return (
            SimpleNamespace(slug="alpha", title="Alpha Course"),
            SimpleNamespace(slug="beta", title="Beta Course"),
            SimpleNamespace(slug="gamma", title="Gamma Course"),
        )


class FakeQuizRepository:
    def __init__(self) -> None:
        self.calls = []

    def get_course_quiz_stats_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
    ):
        self.calls.append((db_path, user_id, course_slug))

        stats = {
            "alpha": {
                "attempts_count": 2,
                "best_score_percent": 80.0,
                "average_score_percent": 70.0,
                "latest_score_percent": 80.0,
                "latest_finished_at": "2026-08-20 12:00:00",
                "latest_passed": True,
                "ever_passed": True,
            },
            "beta": {
                "attempts_count": 1,
                "best_score_percent": 90.0,
                "average_score_percent": 90.0,
                "latest_score_percent": 60.0,
                "latest_finished_at": "2026-08-21 12:00:00",
                "latest_passed": False,
                "ever_passed": True,
            },
            "gamma": {
                "attempts_count": 0,
                "best_score_percent": None,
                "average_score_percent": None,
                "latest_score_percent": None,
                "latest_finished_at": None,
                "latest_passed": False,
                "ever_passed": False,
            },
        }
        return stats[course_slug]


class ManagerEmployeeAnalyticsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.quiz_repository = FakeQuizRepository()
        self.service = ManagerEmployeeAnalyticsService(
            FakeRuntime(),
            self.quiz_repository,
            self.db_path,
        )

    def test_builds_employee_quiz_analytics(self) -> None:
        result = self.service.get_quiz_analytics(42)

        self.assertEqual(result.total_attempts_count, 3)
        self.assertEqual(result.tested_courses_count, 2)
        self.assertEqual(result.passed_courses_count, 2)
        self.assertEqual(result.latest_failed_courses_count, 1)
        self.assertEqual(result.best_score_percent, 90.0)
        self.assertAlmostEqual(result.average_score_percent, 76.67, places=2)

        self.assertEqual(len(result.courses), 2)
        self.assertEqual(result.courses[0].slug, "alpha")
        self.assertEqual(result.courses[1].slug, "beta")

    def test_ignores_courses_without_finished_attempts(self) -> None:
        result = self.service.get_quiz_analytics(42)

        self.assertEqual(
            tuple(course.slug for course in result.courses),
            ("alpha", "beta"),
        )

    def test_queries_every_runtime_course_for_canonical_user(self) -> None:
        self.service.get_quiz_analytics(42)

        self.assertEqual(
            self.quiz_repository.calls,
            [
                (self.db_path, 42, "alpha"),
                (self.db_path, 42, "beta"),
                (self.db_path, 42, "gamma"),
            ],
        )


    def test_returns_empty_analytics_without_finished_attempts(self) -> None:
        class EmptyQuizRepository:
            def get_course_quiz_stats_for_user(
                self,
                db_path,
                user_id,
                course_slug,
            ):
                return {
                    "attempts_count": 0,
                    "best_score_percent": None,
                    "average_score_percent": None,
                    "latest_score_percent": None,
                    "latest_finished_at": None,
                    "latest_passed": False,
                    "ever_passed": False,
                }

        service = ManagerEmployeeAnalyticsService(
            FakeRuntime(),
            EmptyQuizRepository(),
            self.db_path,
        )

        result = service.get_quiz_analytics(42)

        self.assertEqual(result.total_attempts_count, 0)
        self.assertEqual(result.tested_courses_count, 0)
        self.assertEqual(result.passed_courses_count, 0)
        self.assertEqual(result.latest_failed_courses_count, 0)
        self.assertIsNone(result.best_score_percent)
        self.assertIsNone(result.average_score_percent)
        self.assertEqual(result.courses, ())


    def test_rejects_invalid_user_id(self) -> None:
        for invalid_user_id in (0, -1, True, "42"):
            with self.subTest(user_id=invalid_user_id):
                with self.assertRaises(ValueError):
                    self.service.get_quiz_analytics(invalid_user_id)


if __name__ == "__main__":
    unittest.main()
