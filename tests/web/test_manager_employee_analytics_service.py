from types import SimpleNamespace
import unittest
from pathlib import Path
from typing import Optional

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


def _question(
    question_id: str,
    tags: Optional[list[str]] = None,
) -> SimpleNamespace:
    return SimpleNamespace(id=question_id, tags=tags or [])


def _quiz(*questions: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(questions=list(questions))


def _course(
    slug: str,
    *,
    quiz: Optional[SimpleNamespace] = None,
) -> SimpleNamespace:
    return SimpleNamespace(slug=slug, quiz=quiz)


def _answer_row(
    question_id: str,
    *,
    is_correct: bool,
) -> dict[str, object]:
    return {
        "attempt_id": 1,
        "question_id": question_id,
        "is_correct": 1 if is_correct else 0,
        "finished_at": "2026-08-20 12:00:00",
    }


class TopicAnalyticsFakeRuntime:
    def __init__(self, courses: tuple[SimpleNamespace, ...]) -> None:
        self._courses = courses

    def get_courses(self):
        return self._courses


class TopicAnalyticsFakeQuizRepository:
    def __init__(
        self,
        answers_by_course: Optional[dict[str, list[dict[str, object]]]] = None,
    ) -> None:
        self.answers_by_course = answers_by_course or {}
        self.finished_answer_calls: list[tuple[Path, int, str]] = []

    def get_finished_answers_for_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
    ):
        self.finished_answer_calls.append((db_path, user_id, course_slug))
        return self.answers_by_course.get(course_slug, [])


class ManagerEmployeeTopicAnalyticsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")

    def test_aggregates_correct_and_incorrect_answers_across_attempts(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True),
                    _answer_row("q1", is_correct=False),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 2)
        self.assertEqual(len(result.topics), 1)
        topic = result.topics[0]
        self.assertEqual(topic.tag, "Returns")
        self.assertEqual(topic.answers_count, 2)
        self.assertEqual(topic.correct_answers_count, 1)
        self.assertEqual(topic.accuracy_percent, 50.0)

    def test_aggregates_same_tag_across_multiple_courses(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),
                _course("beta", quiz=_quiz(_question("q2", ["Returns"]))),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [_answer_row("q1", is_correct=True)],
                "beta": [_answer_row("q2", is_correct=False)],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 2)
        self.assertEqual(len(result.topics), 1)
        topic = result.topics[0]
        self.assertEqual(topic.tag, "Returns")
        self.assertEqual(topic.answers_count, 2)
        self.assertEqual(topic.correct_answers_count, 1)
        self.assertEqual(topic.accuracy_percent, 50.0)

    def test_one_question_with_multiple_tags_contributes_to_every_tag(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns", "Python"])),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": [_answer_row("q1", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 2)
        self.assertEqual(
            {topic.tag for topic in result.topics},
            {"Returns", "Python"},
        )
        for topic in result.topics:
            self.assertEqual(topic.answers_count, 1)
            self.assertEqual(topic.correct_answers_count, 1)
            self.assertEqual(topic.accuracy_percent, 100.0)

    def test_duplicate_tag_on_one_question_is_counted_once(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns", " Returns ", "Returns"])),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": [_answer_row("q1", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 1)
        self.assertEqual(len(result.topics), 1)
        self.assertEqual(result.topics[0].tag, "Returns")
        self.assertEqual(result.topics[0].answers_count, 1)

    def test_whitespace_only_tags_are_ignored(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["   ", "\t", ""])),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": [_answer_row("q1", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 0)
        self.assertEqual(result.topics, ())

    def test_surrounding_whitespace_is_stripped_from_tags(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["  Returns  "])),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": [_answer_row("q1", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(len(result.topics), 1)
        self.assertEqual(result.topics[0].tag, "Returns")

    def test_questions_without_tags_are_ignored(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course("alpha", quiz=_quiz(_question("q1"))),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": [_answer_row("q1", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 0)
        self.assertEqual(result.topics, ())

    def test_stale_unknown_question_id_is_ignored(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": [_answer_row("missing", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 0)
        self.assertEqual(result.topics, ())

    def test_course_without_quiz_is_skipped(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course("alpha"),
                _course("beta", quiz=_quiz(_question("q1", ["Returns"]))),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {"beta": [_answer_row("q1", is_correct=True)]},
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 1)
        self.assertEqual(
            repository.finished_answer_calls,
            [(self.db_path, 42, "beta")],
        )

    def test_returns_empty_result_when_no_tagged_finished_answers(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository({"alpha": []})
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(result.total_tagged_answers_count, 0)
        self.assertEqual(result.topics, ())

    def test_repository_called_with_canonical_user_id_for_quiz_courses(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),
                _course("beta", quiz=_quiz(_question("q2", ["Python"]))),
                _course("gamma"),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [_answer_row("q1", is_correct=True)],
                "beta": [_answer_row("q2", is_correct=False)],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        service.get_quiz_topics_analytics(42)

        self.assertEqual(
            repository.finished_answer_calls,
            [
                (self.db_path, 42, "alpha"),
                (self.db_path, 42, "beta"),
            ],
        )

    def test_rejects_invalid_user_id_for_topic_analytics(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository()
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        for invalid_user_id in (0, -1, True, "42"):
            with self.subTest(user_id=invalid_user_id):
                with self.assertRaises(ValueError):
                    service.get_quiz_topics_analytics(invalid_user_id)

    def test_topics_are_sorted_deterministically(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(
                        _question("q1", ["beta"]),
                        _question("q2", ["Alpha"]),
                        _question("q3", ["gamma"]),
                        _question("q4", ["delta"]),
                    ),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True),
                    _answer_row("q1", is_correct=True),
                    _answer_row("q2", is_correct=True),
                    _answer_row("q3", is_correct=True),
                    _answer_row("q3", is_correct=False),
                    _answer_row("q4", is_correct=False),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
        )

        result = service.get_quiz_topics_analytics(42)

        self.assertEqual(
            [topic.tag for topic in result.topics],
            ["beta", "Alpha", "gamma", "delta"],
        )
        self.assertEqual(result.topics[0].accuracy_percent, 100.0)
        self.assertEqual(result.topics[0].answers_count, 2)
        self.assertEqual(result.topics[1].accuracy_percent, 100.0)
        self.assertEqual(result.topics[1].answers_count, 1)
        self.assertEqual(result.topics[2].accuracy_percent, 50.0)
        self.assertEqual(result.topics[3].accuracy_percent, 0.0)


if __name__ == "__main__":
    unittest.main()
