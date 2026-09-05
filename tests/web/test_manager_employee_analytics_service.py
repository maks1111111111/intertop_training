from types import SimpleNamespace
import unittest
from pathlib import Path
from typing import Optional

from app.web.manager_employee_analytics_service import (
    DEVELOPMENT_TOPIC_ACCURACY_PERCENT,
    IMPACT_CLASSIFICATION_DECLINED,
    IMPACT_CLASSIFICATION_IMPROVED,
    IMPACT_CLASSIFICATION_INSUFFICIENT_DATA,
    IMPACT_CLASSIFICATION_UNCHANGED,
    MIN_PRACTICAL_SIGNAL_OCCURRENCES,
    MIN_TOPIC_ANSWERS,
    STRONG_TOPIC_ACCURACY_PERCENT,
    EmployeeDevelopmentProfile,
    EmployeePracticalSignal,
    EmployeePracticalTaskAttemptAnalytics,
    EmployeePracticalTaskAnalytics,
    EmployeeQuizTopicCourseEvidence,
    EmployeeQuizTopicEvidence,
    ManagerEmployeeAnalyticsService,
)


class FakeRuntime:
    def get_courses(self):
        return (
            SimpleNamespace(
                slug="alpha",
                title="Alpha Course",
                lessons=(
                    SimpleNamespace(path=SimpleNamespace(name="lesson_01"), title="Lesson One"),
                ),
            ),
            SimpleNamespace(slug="beta", title="Beta Course", lessons=()),
            SimpleNamespace(slug="gamma", title="Gamma Course", lessons=()),
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


class FakePracticalTaskAttempt:
    def __init__(
        self,
        *,
        id: int,
        user_id: int,
        course_slug: str,
        lesson_slug: str,
        task_title: str,
        status: str,
        score=None,
        max_score=None,
        passed=None,
        feedback_summary=None,
        strengths=(),
        improvements=(),
        started_at: str = "2026-08-20 12:00:00",
        reviewed_at=None,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.course_slug = course_slug
        self.lesson_slug = lesson_slug
        self.task_title = task_title
        self.status = status
        self.score = score
        self.max_score = max_score
        self.passed = passed
        self.feedback_summary = feedback_summary
        self.strengths = strengths
        self.improvements = improvements
        self.started_at = started_at
        self.reviewed_at = reviewed_at


class FakePracticalTaskAttemptRepository:
    def __init__(self, attempts=None) -> None:
        self.calls: list[tuple[Path, int, int]] = []
        self.aggregate_calls: list[tuple[Path, int]] = []
        self.reviewed_feedback_calls: list[tuple[Path, int]] = []
        self._attempts = list(attempts or [])
        self._reviewed_feedback = []

    def get_reviewed_feedback_for_user(
        self,
        db_path: Path,
        user_id: int,
    ):
        self.reviewed_feedback_calls.append((db_path, user_id))
        return list(self._reviewed_feedback)

    def get_attempts_aggregate_for_user(
        self,
        db_path: Path,
        user_id: int,
    ):
        self.aggregate_calls.append((db_path, user_id))

        reviewed_attempts_count = 0
        passed_attempts_count = 0
        failed_attempts_count = 0
        pending_attempts_count = 0
        score_percents: list[float] = []

        for attempt in self._attempts:
            if attempt.status == "reviewed":
                reviewed_attempts_count += 1
                if (
                    attempt.score is not None
                    and attempt.max_score is not None
                    and attempt.max_score > 0
                ):
                    score_percents.append(
                        round(attempt.score * 100 / attempt.max_score, 2)
                    )
                if attempt.passed is True:
                    passed_attempts_count += 1
                elif attempt.passed is False:
                    failed_attempts_count += 1
            elif attempt.status == "pending":
                pending_attempts_count += 1

        from app.repositories.practical_task_attempt_repository import (
            PracticalTaskAttemptAggregate,
        )

        return PracticalTaskAttemptAggregate(
            total_attempts_count=len(self._attempts),
            reviewed_attempts_count=reviewed_attempts_count,
            passed_attempts_count=passed_attempts_count,
            failed_attempts_count=failed_attempts_count,
            pending_attempts_count=pending_attempts_count,
            scorable_attempts_count=len(score_percents),
            average_score_percent=(
                round(sum(score_percents) / len(score_percents), 2)
                if score_percents
                else None
            ),
            best_score_percent=max(score_percents) if score_percents else None,
        )

    def get_attempts_for_user(
        self,
        db_path: Path,
        user_id: int,
        limit: int = 10,
    ):
        self.calls.append((db_path, user_id, limit))
        return self._attempts[:limit]


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
    title: Optional[str] = None,
    quiz: Optional[SimpleNamespace] = None,
) -> SimpleNamespace:
    return SimpleNamespace(slug=slug, title=title or slug.replace("_", " ").title(), quiz=quiz)


def _answer_row(
    question_id: str,
    *,
    is_correct: bool,
    finished_at: str = "2026-08-20 12:00:00",
) -> dict[str, object]:
    return {
        "attempt_id": 1,
        "question_id": question_id,
        "is_correct": 1 if is_correct else 0,
        "finished_at": finished_at,
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


def _topic_service(
    db_path: Path,
    *,
    answers_by_course: dict[str, list[dict[str, object]]],
    courses: tuple[SimpleNamespace, ...],
    practical_task_attempt_repository: Optional[FakePracticalTaskAttemptRepository] = None,
) -> tuple[ManagerEmployeeAnalyticsService, TopicAnalyticsFakeQuizRepository]:
    repository = TopicAnalyticsFakeQuizRepository(answers_by_course)
    if practical_task_attempt_repository is None:
        practical_task_attempt_repository = FakePracticalTaskAttemptRepository()
    service = ManagerEmployeeAnalyticsService(
        TopicAnalyticsFakeRuntime(courses),
        repository,
        db_path,
        practical_task_attempt_repository,
    )
    return service, repository


def _answers_for_accuracy(
    question_id: str,
    *,
    correct_count: int,
    incorrect_count: int,
) -> list[dict[str, object]]:
    return [
        *(_answer_row(question_id, is_correct=True) for _ in range(correct_count)),
        *(_answer_row(question_id, is_correct=False) for _ in range(incorrect_count)),
    ]


class ManagerEmployeeTopicClassificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")

    def test_eighty_percent_or_higher_with_minimum_answers_becomes_strength(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            ),
            answers_by_course={
                "alpha": _answers_for_accuracy(
                    "q1",
                    correct_count=8,
                    incorrect_count=2,
                ),
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].tag, "Returns")
        self.assertEqual(result.strengths[0].accuracy_percent, 80.0)
        self.assertEqual(result.development_areas, ())
        self.assertEqual(result.unclassified_topics_count, 0)

    def test_below_seventy_percent_with_minimum_answers_becomes_development_area(
        self,
    ) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            ),
            answers_by_course={
                "alpha": _answers_for_accuracy(
                    "q1",
                    correct_count=2,
                    incorrect_count=1,
                ),
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(result.strengths, ())
        self.assertEqual(len(result.development_areas), 1)
        self.assertEqual(result.development_areas[0].tag, "Returns")
        self.assertAlmostEqual(result.development_areas[0].accuracy_percent, 66.67, places=2)
        self.assertEqual(result.unclassified_topics_count, 0)

    def test_exactly_seventy_percent_is_neutral(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            ),
            answers_by_course={
                "alpha": _answers_for_accuracy(
                    "q1",
                    correct_count=7,
                    incorrect_count=3,
                ),
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(result.strengths, ())
        self.assertEqual(result.development_areas, ())
        self.assertEqual(result.unclassified_topics_count, 1)

    def test_exactly_eighty_percent_is_strength(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            ),
            answers_by_course={
                "alpha": _answers_for_accuracy(
                    "q1",
                    correct_count=4,
                    incorrect_count=1,
                ),
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].accuracy_percent, 80.0)
        self.assertEqual(result.development_areas, ())
        self.assertEqual(result.unclassified_topics_count, 0)

    def test_topic_with_fewer_than_minimum_answers_is_unclassified(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            ),
            answers_by_course={
                "alpha": _answers_for_accuracy(
                    "q1",
                    correct_count=2,
                    incorrect_count=0,
                ),
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(result.strengths, ())
        self.assertEqual(result.development_areas, ())
        self.assertEqual(result.unclassified_topics_count, 1)

    def test_neutral_and_low_sample_topics_are_counted_as_unclassified(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(
                        _question("q1", ["Strong"]),
                        _question("q2", ["Neutral"]),
                        _question("q3", ["LowSample"]),
                    ),
                ),
            ),
            answers_by_course={
                "alpha": [
                    *_answers_for_accuracy("q1", correct_count=3, incorrect_count=0),
                    *_answers_for_accuracy("q2", correct_count=7, incorrect_count=3),
                    *_answers_for_accuracy("q3", correct_count=2, incorrect_count=0),
                ],
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].tag, "Strong")
        self.assertEqual(result.development_areas, ())
        self.assertEqual(result.unclassified_topics_count, 2)

    def test_strengths_are_sorted_deterministically(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(
                        _question("q1", ["beta"]),
                        _question("q2", ["Alpha"]),
                        _question("q3", ["gamma"]),
                    ),
                ),
            ),
            answers_by_course={
                "alpha": [
                    *_answers_for_accuracy("q1", correct_count=4, incorrect_count=0),
                    *_answers_for_accuracy("q2", correct_count=3, incorrect_count=0),
                    *_answers_for_accuracy("q3", correct_count=4, incorrect_count=1),
                ],
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(
            [topic.tag for topic in result.strengths],
            ["beta", "Alpha", "gamma"],
        )
        self.assertEqual(result.strengths[0].accuracy_percent, 100.0)
        self.assertEqual(result.strengths[0].answers_count, 4)
        self.assertEqual(result.strengths[1].accuracy_percent, 100.0)
        self.assertEqual(result.strengths[1].answers_count, 3)
        self.assertEqual(result.strengths[2].accuracy_percent, 80.0)

    def test_development_areas_are_sorted_deterministically(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(
                _course(
                    "alpha",
                    quiz=_quiz(
                        _question("q1", ["beta"]),
                        _question("q2", ["Alpha"]),
                        _question("q3", ["gamma"]),
                    ),
                ),
            ),
            answers_by_course={
                "alpha": [
                    *_answers_for_accuracy("q1", correct_count=1, incorrect_count=2),
                    *_answers_for_accuracy("q2", correct_count=1, incorrect_count=2),
                    *_answers_for_accuracy("q3", correct_count=0, incorrect_count=4),
                ],
            },
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(
            [topic.tag for topic in result.development_areas],
            ["gamma", "Alpha", "beta"],
        )
        self.assertEqual(result.development_areas[0].accuracy_percent, 0.0)
        self.assertAlmostEqual(result.development_areas[1].accuracy_percent, 33.33, places=2)
        self.assertAlmostEqual(result.development_areas[2].accuracy_percent, 33.33, places=2)
        self.assertEqual(result.development_areas[1].answers_count, 3)
        self.assertEqual(result.development_areas[2].answers_count, 3)

    def test_empty_topic_analytics_returns_empty_classification(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),),
            answers_by_course={"alpha": []},
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(result.strengths, ())
        self.assertEqual(result.development_areas, ())
        self.assertEqual(result.unclassified_topics_count, 0)

    def test_rejects_invalid_user_id_for_topic_classification(self) -> None:
        service, _ = _topic_service(
            self.db_path,
            courses=(_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),),
            answers_by_course={"alpha": []},
        )

        for invalid_user_id in (0, -1, True, "42"):
            with self.subTest(user_id=invalid_user_id):
                with self.assertRaises(ValueError):
                    service.get_quiz_topic_classification(invalid_user_id)

    def test_reuses_topic_analytics_without_duplicating_repository_logic(self) -> None:
        class CountingService(ManagerEmployeeAnalyticsService):
            topic_analytics_calls = 0

            def get_quiz_topics_analytics(self, user_id: int):
                CountingService.topic_analytics_calls += 1
                return super().get_quiz_topics_analytics(user_id)

        CountingService.topic_analytics_calls = 0
        service = CountingService(
            TopicAnalyticsFakeRuntime(
                (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
            ),
            TopicAnalyticsFakeQuizRepository(
                {"alpha": _answers_for_accuracy("q1", correct_count=3, incorrect_count=0)},
            ),
            self.db_path,
        )

        result = service.get_quiz_topic_classification(42)

        self.assertEqual(CountingService.topic_analytics_calls, 1)
        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].tag, "Returns")

    def test_classification_constants_match_requirements(self) -> None:
        self.assertEqual(MIN_TOPIC_ANSWERS, 3)
        self.assertEqual(STRONG_TOPIC_ACCURACY_PERCENT, 80.0)
        self.assertEqual(DEVELOPMENT_TOPIC_ACCURACY_PERCENT, 70.0)


class ManagerEmployeePracticalTaskAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.practical_repository = FakePracticalTaskAttemptRepository()
        self.service = ManagerEmployeeAnalyticsService(
            FakeRuntime(),
            FakeQuizRepository(),
            self.db_path,
            self.practical_repository,
        )

    def test_builds_practical_task_aggregate_counts(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Passed task",
                status="reviewed",
                score=8,
                max_score=10,
                passed=True,
                feedback_summary="Good work",
            ),
            FakePracticalTaskAttempt(
                id=2,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Failed task",
                status="reviewed",
                score=4,
                max_score=10,
                passed=False,
                feedback_summary="Needs improvement",
            ),
            FakePracticalTaskAttempt(
                id=3,
                user_id=42,
                course_slug="stale-course",
                lesson_slug="missing-lesson",
                task_title="Pending task",
                status="pending",
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.total_attempts_count, 3)
        self.assertEqual(result.reviewed_attempts_count, 2)
        self.assertEqual(result.passed_attempts_count, 1)
        self.assertEqual(result.failed_attempts_count, 1)
        self.assertEqual(result.pending_attempts_count, 1)
        self.assertEqual(result.average_score_percent, 60.0)
        self.assertEqual(result.best_score_percent, 80.0)
        self.assertEqual(result.scorable_attempts_count, 2)

    def test_exposes_scorable_attempts_count_for_team_weighting(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Scored",
                status="reviewed",
                score=8,
                max_score=10,
                passed=True,
            ),
            FakePracticalTaskAttempt(
                id=2,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_02",
                task_title="Unscorable",
                status="reviewed",
                score=None,
                max_score=None,
                passed=False,
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.scorable_attempts_count, 1)

    def test_normalizes_score_percent_from_score_and_max_score(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Scored task",
                status="reviewed",
                score=7,
                max_score=8,
                passed=True,
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.recent_attempts[0].score_percent, 87.5)

    def test_average_percent_excludes_pending_and_unscorable_rows(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Scored task",
                status="reviewed",
                score=10,
                max_score=10,
                passed=True,
            ),
            FakePracticalTaskAttempt(
                id=2,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Pending task",
                status="pending",
            ),
            FakePracticalTaskAttempt(
                id=3,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Broken score",
                status="reviewed",
                score=None,
                max_score=10,
                passed=False,
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.average_score_percent, 100.0)
        self.assertEqual(result.best_score_percent, 100.0)

    def test_recent_rows_resolve_course_and_lesson_titles(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Resolved task",
                status="reviewed",
                score=8,
                max_score=10,
                passed=True,
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.recent_attempts[0].course_title, "Alpha Course")
        self.assertEqual(result.recent_attempts[0].lesson_title, "Lesson One")

    def test_stale_course_and_lesson_references_do_not_crash(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="missing-course",
                lesson_slug="missing-lesson",
                task_title="Stored title",
                status="pending",
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.recent_attempts[0].course_title, "missing-course")
        self.assertEqual(result.recent_attempts[0].lesson_title, "missing-lesson")
        self.assertEqual(result.recent_attempts[0].task_title, "Stored title")

    def test_invalid_user_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_practical_task_analytics(0)

    def test_repository_called_with_canonical_user_id(self) -> None:
        self.service.get_practical_task_analytics(42)

        self.assertEqual(
            self.practical_repository.aggregate_calls,
            [(self.db_path, 42)],
        )
        self.assertEqual(
            self.practical_repository.calls,
            [(self.db_path, 42, 10)],
        )

    def test_aggregates_are_not_limited_by_recent_display_limit(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=index,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title=f"Task {index}",
                status="reviewed",
                score=8,
                max_score=10,
                passed=True,
            )
            for index in range(1, 6)
        ]

        result = self.service.get_practical_task_analytics(42, limit=2)

        self.assertEqual(result.total_attempts_count, 5)
        self.assertEqual(result.reviewed_attempts_count, 5)
        self.assertEqual(len(result.recent_attempts), 2)
        self.assertEqual(
            self.practical_repository.aggregate_calls,
            [(self.db_path, 42)],
        )
        self.assertEqual(
            self.practical_repository.calls,
            [(self.db_path, 42, 2)],
        )

    def test_unknown_statuses_are_not_counted_as_failed(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=1,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title="Legacy task",
                status="legacy",
            ),
        ]

        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.total_attempts_count, 1)
        self.assertEqual(result.failed_attempts_count, 0)
        self.assertEqual(result.pending_attempts_count, 0)
        self.assertEqual(result.reviewed_attempts_count, 0)

    def test_recent_attempts_respect_limit(self) -> None:
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=index,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title=f"Task {index}",
                status="pending",
            )
            for index in range(1, 4)
        ]

        result = self.service.get_practical_task_analytics(42, limit=2)

        self.assertEqual(len(result.recent_attempts), 2)
        self.assertEqual(result.total_attempts_count, 3)

    def test_empty_result_when_no_attempts(self) -> None:
        result = self.service.get_practical_task_analytics(42)

        self.assertEqual(result.total_attempts_count, 0)
        self.assertIsNone(result.average_score_percent)
        self.assertEqual(result.recent_attempts, ())


class FakeReviewFeedback:
    def __init__(
        self,
        *,
        id: int,
        status: str = "reviewed",
        course_slug: str = "alpha",
        lesson_slug: str = "lesson_01",
        strengths=(),
        improvements=(),
        reviewed_at: Optional[str] = "2026-08-20 12:00:00",
    ) -> None:
        self.id = id
        self.status = status
        self.course_slug = course_slug
        self.lesson_slug = lesson_slug
        self.strengths = strengths
        self.improvements = improvements
        self.reviewed_at = reviewed_at


class ManagerEmployeeDevelopmentProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.practical_repository = FakePracticalTaskAttemptRepository()
        self.service = ManagerEmployeeAnalyticsService(
            TopicAnalyticsFakeRuntime(
                (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
            ),
            TopicAnalyticsFakeQuizRepository(
                {"alpha": _answers_for_accuracy("q1", correct_count=4, incorrect_count=0)},
            ),
            self.db_path,
            self.practical_repository,
        )

    def _development_service(
        self,
        feedback_rows: list[FakeReviewFeedback],
    ) -> ManagerEmployeeAnalyticsService:
        self.practical_repository._reviewed_feedback = feedback_rows
        return self.service

    def test_one_reviewed_attempt_does_not_create_recurring_practical_signals(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(
                    id=1,
                    strengths=("Clear communication",),
                    improvements=("Add detail",),
                ),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(result.practical_strengths, ())
        self.assertEqual(result.practical_development_areas, ())
        self.assertEqual(result.reviewed_practical_attempts_count, 1)
        self.assertFalse(result.has_sufficient_practical_evidence)

    def test_same_strength_in_two_reviewed_attempts_becomes_recurring_strength(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(id=1, strengths=("Clear communication",)),
                FakeReviewFeedback(id=2, strengths=("Clear communication",)),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(len(result.practical_strengths), 1)
        self.assertEqual(result.practical_strengths[0].text, "Clear communication")
        self.assertEqual(result.practical_strengths[0].evidence_count, 2)
        self.assertTrue(result.has_sufficient_practical_evidence)

    def test_same_improvement_in_three_reviewed_attempts_counts_three(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(id=1, improvements=("Add detail",)),
                FakeReviewFeedback(id=2, improvements=("Add detail",)),
                FakeReviewFeedback(id=3, improvements=("Add detail",)),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(len(result.practical_development_areas), 1)
        self.assertEqual(result.practical_development_areas[0].text, "Add detail")
        self.assertEqual(result.practical_development_areas[0].evidence_count, 3)

    def test_whitespace_and_case_normalization_merge_equivalent_text(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(id=1, strengths=("  Clear   communication ",)),
                FakeReviewFeedback(id=2, strengths=("clear communication",)),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(len(result.practical_strengths), 1)
        self.assertEqual(result.practical_strengths[0].text, "Clear communication")
        self.assertEqual(result.practical_strengths[0].evidence_count, 2)

    def test_duplicate_signal_inside_same_attempt_counts_once(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(
                    id=1,
                    strengths=("Clear communication", "clear communication"),
                ),
                FakeReviewFeedback(id=2, strengths=("Clear communication",)),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(len(result.practical_strengths), 1)
        self.assertEqual(result.practical_strengths[0].evidence_count, 2)

    def test_empty_and_whitespace_signals_are_ignored(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(id=1, strengths=("   ", 123, "Valid signal")),
                FakeReviewFeedback(id=2, strengths=("Valid signal",)),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(len(result.practical_strengths), 1)
        self.assertEqual(result.practical_strengths[0].text, "Valid signal")

    def test_pending_and_non_reviewed_feedback_is_ignored(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, status="reviewed", strengths=("Valid signal",)),
        ]

        result = self.service.get_development_profile(42)

        self.assertEqual(result.reviewed_practical_attempts_count, 1)

    def test_reviewed_practical_attempts_count_uses_all_reviewed_feedback(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(id=1),
                FakeReviewFeedback(id=2),
                FakeReviewFeedback(id=3),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(result.reviewed_practical_attempts_count, 3)
        self.assertTrue(result.has_sufficient_practical_evidence)

    def test_development_profile_is_independent_of_recent_display_limit(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, strengths=("Signal one",)),
            FakeReviewFeedback(id=2, strengths=("Signal one",)),
            FakeReviewFeedback(id=3, strengths=("Signal two",)),
        ]
        self.practical_repository._attempts = [
            FakePracticalTaskAttempt(
                id=index,
                user_id=42,
                course_slug="alpha",
                lesson_slug="lesson_01",
                task_title=f"Task {index}",
                status="reviewed",
                score=8,
                max_score=10,
                passed=True,
            )
            for index in range(1, 3)
        ]

        result = self.service.get_development_profile(42)

        self.assertEqual(result.reviewed_practical_attempts_count, 3)
        self.assertEqual(len(result.practical_strengths), 1)
        self.assertEqual(result.practical_strengths[0].evidence_count, 2)
        self.assertEqual(
            self.practical_repository.reviewed_feedback_calls,
            [(self.db_path, 42)],
        )
        self.assertEqual(self.practical_repository.calls, [])

    def test_practical_signals_are_sorted_deterministically(self) -> None:
        service = self._development_service(
            [
                FakeReviewFeedback(
                    id=1,
                    strengths=("beta signal", "Alpha signal", "gamma signal"),
                ),
                FakeReviewFeedback(
                    id=2,
                    strengths=("beta signal", "Alpha signal", "gamma signal"),
                ),
                FakeReviewFeedback(id=3, strengths=("gamma signal",)),
            ]
        )

        result = service.get_development_profile(42)

        self.assertEqual(
            [signal.text for signal in result.practical_strengths],
            ["gamma signal", "Alpha signal", "beta signal"],
        )
        self.assertEqual(result.practical_strengths[0].evidence_count, 3)
        self.assertEqual(result.practical_strengths[1].evidence_count, 2)

    def test_invalid_user_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_development_profile(0)

    def test_repository_called_with_canonical_user_id(self) -> None:
        self.service.get_development_profile(42)

        self.assertEqual(
            self.practical_repository.reviewed_feedback_calls,
            [(self.db_path, 42)],
        )

    def test_development_profile_uses_single_quiz_repository_traversal(self) -> None:
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": _answers_for_accuracy("q1", correct_count=4, incorrect_count=0)},
        )
        service = ManagerEmployeeAnalyticsService(
            TopicAnalyticsFakeRuntime(
                (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
            ),
            repository,
            self.db_path,
            FakePracticalTaskAttemptRepository(),
        )

        result = service.get_development_profile(42)

        self.assertEqual(
            repository.finished_answer_calls,
            [(self.db_path, 42, "alpha")],
        )
        self.assertEqual(len(result.quiz_strengths), 1)
        self.assertEqual(result.quiz_strengths[0].tag, "Returns")
        self.assertEqual(len(result.quiz_strength_evidence), 1)
        self.assertEqual(result.quiz_strength_evidence[0].tag, "Returns")

    def test_includes_quiz_classification_without_duplicating_repository_logic(self) -> None:
        service = self._development_service([])

        result = service.get_development_profile(42)
        classification = service.get_quiz_topic_classification(42)

        self.assertEqual(result.quiz_strengths, classification.strengths)
        self.assertEqual(result.quiz_development_areas, classification.development_areas)

    def test_development_profile_constants_match_requirements(self) -> None:
        self.assertEqual(MIN_PRACTICAL_SIGNAL_OCCURRENCES, 2)


class ManagerEmployeePracticalSignalEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.practical_repository = FakePracticalTaskAttemptRepository()
        self.service = ManagerEmployeeAnalyticsService(
            TopicAnalyticsFakeRuntime(()),
            TopicAnalyticsFakeQuizRepository({}),
            self.db_path,
            self.practical_repository,
        )

    def test_returns_single_occurrence_signals_without_filtering(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, strengths=("Single signal",)),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].text, "Single signal")
        self.assertEqual(result.strengths[0].evidence_count, 1)

    def test_duplicate_signal_inside_same_attempt_counts_once(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                strengths=("Clear communication", "clear communication"),
            ),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].evidence_count, 1)

    def test_same_normalized_signal_across_attempts_increments_evidence(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, improvements=("Add detail",)),
            FakeReviewFeedback(id=2, improvements=("Add detail",)),
            FakeReviewFeedback(id=3, improvements=("Add detail",)),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual(len(result.development_areas), 1)
        self.assertEqual(result.development_areas[0].evidence_count, 3)

    def test_case_and_whitespace_variants_merge(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, strengths=("  Clear   communication ",)),
            FakeReviewFeedback(id=2, strengths=("clear communication",)),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].text, "Clear communication")
        self.assertEqual(result.strengths[0].evidence_count, 2)

    def test_empty_values_are_ignored(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, strengths=("   ", 123, "Valid signal")),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual(len(result.strengths), 1)
        self.assertEqual(result.strengths[0].text, "Valid signal")

    def test_invalid_user_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_practical_signal_evidence(0)

    def test_repository_called_with_canonical_user_id(self) -> None:
        self.service.get_practical_signal_evidence(42)

        self.assertEqual(
            self.practical_repository.reviewed_feedback_calls,
            [(self.db_path, 42)],
        )

    def test_reviewed_attempts_count_reflects_all_feedback_rows(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1),
            FakeReviewFeedback(id=2),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual(result.reviewed_attempts_count, 2)

    def test_strengths_and_development_areas_are_separate(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                strengths=("Strength signal",),
                improvements=("Improvement signal",),
            ),
        ]

        result = self.service.get_practical_signal_evidence(42)

        self.assertEqual([signal.text for signal in result.strengths], ["Strength signal"])
        self.assertEqual(
            [signal.text for signal in result.development_areas],
            ["Improvement signal"],
        )

    def test_development_profile_reuses_evidence_api(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, strengths=("Recurring signal",)),
            FakeReviewFeedback(id=2, strengths=("Recurring signal",)),
        ]

        evidence = self.service.get_practical_signal_evidence(42)
        profile = self.service.get_development_profile(42)

        self.assertEqual(len(profile.practical_strengths), 1)
        self.assertEqual(profile.practical_strengths[0].text, "Recurring signal")
        self.assertEqual(
            profile.practical_strengths[0].evidence_count,
            evidence.strengths[0].evidence_count,
        )


class ManagerEmployeePracticalSignalSourceEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.practical_repository = FakePracticalTaskAttemptRepository()
        self.runtime = TopicAnalyticsFakeRuntime(
            (
                SimpleNamespace(
                    slug="alpha",
                    title="Alpha Course",
                    quiz=None,
                    lessons=(
                        SimpleNamespace(
                            path=SimpleNamespace(name="lesson_01"),
                            title="Lesson One",
                        ),
                    ),
                ),
                SimpleNamespace(
                    slug="beta",
                    title="Beta Course",
                    quiz=None,
                    lessons=(
                        SimpleNamespace(
                            path=SimpleNamespace(name="lesson_02"),
                            title="Lesson Two",
                        ),
                    ),
                ),
            )
        )
        self.service = ManagerEmployeeAnalyticsService(
            self.runtime,
            TopicAnalyticsFakeQuizRepository({}),
            self.db_path,
            self.practical_repository,
        )

    def _set_feedback(self, feedback_rows: list[FakeReviewFeedback]) -> None:
        self.practical_repository._reviewed_feedback = feedback_rows

    def test_same_improvement_in_two_attempts_same_lesson_has_one_source(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    course_slug="alpha",
                    lesson_slug="lesson_01",
                    improvements=("Add detail",),
                ),
                FakeReviewFeedback(
                    id=2,
                    course_slug="alpha",
                    lesson_slug="lesson_01",
                    improvements=("Add detail",),
                ),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)
        profile = self.service.get_development_profile(42)

        self.assertEqual(len(evidence.development_areas), 1)
        signal = evidence.development_areas[0]
        self.assertEqual(signal.text, "Add detail")
        self.assertEqual(signal.evidence_count, 2)
        self.assertEqual(len(signal.sources), 1)
        self.assertEqual(signal.sources[0].course_slug, "alpha")
        self.assertEqual(signal.sources[0].lesson_slug, "lesson_01")
        self.assertEqual(signal.sources[0].course_title, "Alpha Course")
        self.assertEqual(signal.sources[0].lesson_title, "Lesson One")
        self.assertEqual(signal.sources[0].evidence_count, 2)

        self.assertEqual(len(profile.practical_development_evidence), 1)
        profile_signal = profile.practical_development_evidence[0]
        self.assertEqual(profile_signal.text, "Add detail")
        self.assertEqual(len(profile_signal.sources), 1)
        self.assertEqual(profile_signal.sources[0].evidence_count, 2)

    def test_same_improvement_across_two_lessons_has_multiple_sources(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    course_slug="alpha",
                    lesson_slug="lesson_01",
                    improvements=("Add detail",),
                ),
                FakeReviewFeedback(
                    id=2,
                    course_slug="beta",
                    lesson_slug="lesson_02",
                    improvements=("Add detail",),
                ),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)
        profile = self.service.get_development_profile(42)

        self.assertEqual(evidence.development_areas[0].evidence_count, 2)
        self.assertEqual(len(evidence.development_areas[0].sources), 2)
        self.assertEqual(
            [source.course_slug for source in evidence.development_areas[0].sources],
            ["alpha", "beta"],
        )
        self.assertEqual(
            [source.lesson_slug for source in evidence.development_areas[0].sources],
            ["lesson_01", "lesson_02"],
        )
        self.assertEqual(len(profile.practical_development_evidence), 1)
        self.assertEqual(len(profile.practical_development_evidence[0].sources), 2)

    def test_duplicate_signal_inside_same_attempt_counts_once_for_source(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail", "add detail"),
                ),
                FakeReviewFeedback(id=2, improvements=("Add detail",)),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)

        self.assertEqual(evidence.development_areas[0].evidence_count, 2)
        self.assertEqual(evidence.development_areas[0].sources[0].evidence_count, 2)

    def test_case_and_whitespace_variants_merge_provenance(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("  Add   detail ",),
                ),
                FakeReviewFeedback(
                    id=2,
                    improvements=("add detail",),
                ),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)

        self.assertEqual(len(evidence.development_areas), 1)
        self.assertEqual(evidence.development_areas[0].text, "Add detail")
        self.assertEqual(evidence.development_areas[0].evidence_count, 2)
        self.assertEqual(evidence.development_areas[0].sources[0].evidence_count, 2)

    def test_non_recurring_signal_excluded_from_development_profile_evidence(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(id=1, improvements=("Single occurrence",)),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)
        profile = self.service.get_development_profile(42)

        self.assertEqual(len(evidence.development_areas), 1)
        self.assertEqual(evidence.development_areas[0].evidence_count, 1)
        self.assertEqual(profile.practical_development_evidence, ())
        self.assertEqual(profile.practical_development_areas, ())

    def test_stale_runtime_content_uses_slug_fallback_titles(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    course_slug="missing-course",
                    lesson_slug="missing-lesson",
                    improvements=("Add detail",),
                ),
                FakeReviewFeedback(
                    id=2,
                    course_slug="missing-course",
                    lesson_slug="missing-lesson",
                    improvements=("Add detail",),
                ),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)

        source = evidence.development_areas[0].sources[0]
        self.assertEqual(source.course_title, "missing-course")
        self.assertEqual(source.lesson_title, "missing-lesson")

    def test_strength_and_development_evidence_are_separated(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    strengths=("Strong empathy",),
                    improvements=("Add detail",),
                ),
                FakeReviewFeedback(
                    id=2,
                    strengths=("Strong empathy",),
                    improvements=("Add detail",),
                ),
            ]
        )

        profile = self.service.get_development_profile(42)

        self.assertEqual(len(profile.practical_strength_evidence), 1)
        self.assertEqual(profile.practical_strength_evidence[0].text, "Strong empathy")
        self.assertEqual(len(profile.practical_development_evidence), 1)
        self.assertEqual(profile.practical_development_evidence[0].text, "Add detail")

    def test_source_ordering_is_deterministic(self) -> None:
        self._set_feedback(
            [
                FakeReviewFeedback(
                    id=1,
                    course_slug="beta",
                    lesson_slug="lesson_02",
                    improvements=("Add detail",),
                ),
                FakeReviewFeedback(
                    id=2,
                    course_slug="alpha",
                    lesson_slug="lesson_01",
                    improvements=("Add detail",),
                ),
                FakeReviewFeedback(
                    id=3,
                    course_slug="alpha",
                    lesson_slug="lesson_01",
                    improvements=("Add detail",),
                ),
            ]
        )

        evidence = self.service.get_practical_signal_evidence(42)
        sources = evidence.development_areas[0].sources

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0].course_slug, "alpha")
        self.assertEqual(sources[0].evidence_count, 2)
        self.assertEqual(sources[1].course_slug, "beta")
        self.assertEqual(sources[1].evidence_count, 1)


class ManagerEmployeeQuizTopicEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")

    def test_one_topic_from_one_course_in_development_profile(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": _answers_for_accuracy("q1", correct_count=4, incorrect_count=0),
            },
            courses=(
                _course(
                    "alpha",
                    title="Alpha Course",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
            ),
        )

        profile = service.get_development_profile(42)

        self.assertEqual(len(profile.quiz_strength_evidence), 1)
        evidence = profile.quiz_strength_evidence[0]
        self.assertEqual(evidence.tag, "Returns")
        self.assertEqual(len(evidence.courses), 1)
        course = evidence.courses[0]
        self.assertEqual(course.course_slug, "alpha")
        self.assertEqual(course.course_title, "Alpha Course")
        self.assertEqual(course.answers_count, 4)
        self.assertEqual(course.correct_answers_count, 4)
        self.assertEqual(course.accuracy_percent, 100.0)

    def test_same_topic_aggregated_from_two_courses(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": _answers_for_accuracy("q1", correct_count=3, incorrect_count=0),
                "beta": _answers_for_accuracy("q2", correct_count=3, incorrect_count=0),
            },
            courses=(
                _course(
                    "alpha",
                    title="Alpha Course",
                    quiz=_quiz(_question("q1", ["Returns"])),
                ),
                _course(
                    "beta",
                    title="Beta Course",
                    quiz=_quiz(_question("q2", ["Returns"])),
                ),
            ),
        )

        profile = service.get_development_profile(42)

        self.assertEqual(len(profile.quiz_strength_evidence), 1)
        self.assertEqual(profile.quiz_development_evidence, ())
        evidence = profile.quiz_strength_evidence[0]
        self.assertEqual(evidence.tag, "Returns")
        self.assertEqual(len(evidence.courses), 2)
        courses_by_slug = {course.course_slug: course for course in evidence.courses}
        self.assertEqual(courses_by_slug["alpha"].course_title, "Alpha Course")
        self.assertEqual(courses_by_slug["beta"].course_title, "Beta Course")
        self.assertEqual(courses_by_slug["alpha"].answers_count, 3)
        self.assertEqual(courses_by_slug["alpha"].accuracy_percent, 100.0)
        self.assertEqual(courses_by_slug["beta"].answers_count, 3)
        self.assertEqual(courses_by_slug["beta"].accuracy_percent, 100.0)

    def test_course_rows_have_correct_counts_and_accuracy(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": [
                    _answer_row("q1", is_correct=True),
                    _answer_row("q1", is_correct=True),
                    _answer_row("q1", is_correct=False),
                ],
            },
            courses=(
                _course("alpha", title="Alpha Course", quiz=_quiz(_question("q1", ["Returns"]))),
            ),
        )

        profile = service.get_development_profile(42)

        course = profile.quiz_development_evidence[0].courses[0]
        self.assertEqual(course.answers_count, 3)
        self.assertEqual(course.correct_answers_count, 2)
        self.assertEqual(course.accuracy_percent, 66.67)

    def test_course_evidence_ordering_is_deterministic(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": _answers_for_accuracy("q1", correct_count=3, incorrect_count=0),
                "beta": _answers_for_accuracy("q2", correct_count=4, incorrect_count=0),
                "gamma": _answers_for_accuracy("q3", correct_count=4, incorrect_count=0),
            },
            courses=(
                _course("alpha", title="Zulu Course", quiz=_quiz(_question("q1", ["Returns"]))),
                _course("beta", title="Alpha Course", quiz=_quiz(_question("q2", ["Returns"]))),
                _course("gamma", title="Beta Course", quiz=_quiz(_question("q3", ["Returns"]))),
            ),
        )

        profile = service.get_development_profile(42)

        course_titles = [course.course_title for course in profile.quiz_strength_evidence[0].courses]
        self.assertEqual(course_titles, ["Alpha Course", "Beta Course", "Zulu Course"])

    def test_stale_question_ids_are_ignored_in_evidence(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": [
                    _answer_row("missing", is_correct=True),
                    *_answers_for_accuracy("q1", correct_count=3, incorrect_count=0),
                ],
            },
            courses=(
                _course("alpha", title="Alpha Course", quiz=_quiz(_question("q1", ["Returns"]))),
            ),
        )

        profile = service.get_development_profile(42)

        self.assertEqual(len(profile.quiz_strength_evidence), 1)
        self.assertEqual(profile.quiz_strength_evidence[0].courses[0].answers_count, 3)

    def test_unclassified_topic_excluded_from_development_profile_evidence(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": _answers_for_accuracy("q1", correct_count=1, incorrect_count=1),
            },
            courses=(
                _course("alpha", title="Alpha Course", quiz=_quiz(_question("q1", ["Returns"]))),
            ),
        )

        profile = service.get_development_profile(42)

        self.assertEqual(profile.quiz_strength_evidence, ())
        self.assertEqual(profile.quiz_development_evidence, ())
        self.assertEqual(profile.quiz_strengths, ())
        self.assertEqual(profile.quiz_development_areas, ())

    def test_strength_and_development_evidence_are_separated(self) -> None:
        service, _repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": _answers_for_accuracy("q1", correct_count=4, incorrect_count=0),
                "beta": _answers_for_accuracy("q2", correct_count=0, incorrect_count=4),
            },
            courses=(
                _course(
                    "alpha",
                    title="Strength Course",
                    quiz=_quiz(_question("q1", ["Strong Topic"])),
                ),
                _course(
                    "beta",
                    title="Development Course",
                    quiz=_quiz(_question("q2", ["Weak Topic"])),
                ),
            ),
        )

        profile = service.get_development_profile(42)

        self.assertEqual([item.tag for item in profile.quiz_strength_evidence], ["Strong Topic"])
        self.assertEqual(
            [item.tag for item in profile.quiz_development_evidence],
            ["Weak Topic"],
        )
        self.assertEqual(
            profile.quiz_strength_evidence[0].courses[0].course_title,
            "Strength Course",
        )
        self.assertEqual(
            profile.quiz_development_evidence[0].courses[0].course_title,
            "Development Course",
        )

    def test_development_profile_reuses_single_repository_traversal(self) -> None:
        repository = TopicAnalyticsFakeQuizRepository(
            {"alpha": _answers_for_accuracy("q1", correct_count=4, incorrect_count=0)},
        )
        service = ManagerEmployeeAnalyticsService(
            TopicAnalyticsFakeRuntime(
                (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
            ),
            repository,
            self.db_path,
            FakePracticalTaskAttemptRepository(),
        )

        service.get_development_profile(42)

        self.assertEqual(
            repository.finished_answer_calls,
            [(self.db_path, 42, "alpha")],
        )

    def test_sequential_development_profiles_for_different_users_do_not_reuse_data(
        self,
    ) -> None:
        class UserScopedQuizRepository:
            def __init__(self) -> None:
                self.finished_answer_calls: list[tuple[Path, int, str]] = []

            def get_finished_answers_for_user(
                self,
                db_path: Path,
                user_id: int,
                course_slug: str,
            ):
                self.finished_answer_calls.append((db_path, user_id, course_slug))
                if user_id == 42:
                    return _answers_for_accuracy("q1", correct_count=4, incorrect_count=0)
                if user_id == 99:
                    return _answers_for_accuracy("q1", correct_count=0, incorrect_count=4)
                return []

        repository = UserScopedQuizRepository()
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            FakePracticalTaskAttemptRepository(),
        )

        profile_42 = service.get_development_profile(42)
        profile_99 = service.get_development_profile(99)

        self.assertEqual(len(profile_42.quiz_strengths), 1)
        self.assertEqual(profile_42.quiz_strengths[0].tag, "Returns")
        self.assertEqual(len(profile_99.quiz_development_areas), 1)
        self.assertEqual(profile_99.quiz_development_areas[0].tag, "Returns")
        self.assertEqual(
            repository.finished_answer_calls,
            [
                (self.db_path, 42, "alpha"),
                (self.db_path, 99, "alpha"),
            ],
        )

    def test_topic_analytics_public_behavior_unchanged(self) -> None:
        service, repository = _topic_service(
            self.db_path,
            answers_by_course={
                "alpha": _answers_for_accuracy("q1", correct_count=4, incorrect_count=0),
            },
            courses=(
                _course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),
            ),
        )

        topics = service.get_quiz_topics_analytics(42)
        classification = service.get_quiz_topic_classification(42)
        profile = service.get_development_profile(42)

        self.assertEqual(profile.quiz_strengths, classification.strengths)
        self.assertEqual(profile.quiz_development_areas, classification.development_areas)
        self.assertEqual(profile.quiz_strengths[0], topics.topics[0])
        self.assertEqual(
            repository.finished_answer_calls.count((self.db_path, 42, "alpha")),
            3,
        )


class ManagerEmployeeDevelopmentImpactEvidenceTests(unittest.TestCase):
    ASSIGNED_AT = "2026-09-15 12:00:00"

    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.quiz_repository = TopicAnalyticsFakeQuizRepository({})
        self.practical_repository = FakePracticalTaskAttemptRepository()
        self.service = ManagerEmployeeAnalyticsService(
            TopicAnalyticsFakeRuntime(()),
            self.quiz_repository,
            self.db_path,
            self.practical_repository,
        )

    def test_quiz_evidence_only_before_assignment(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row(
                        "q1",
                        is_correct=True,
                        finished_at="2026-09-10 10:00:00",
                    ),
                    _answer_row(
                        "q1",
                        is_correct=False,
                        finished_at="2026-09-14 11:00:00",
                    ),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        self.assertIsNotNone(result.quiz)
        self.assertIsNone(result.practical)
        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.tag, "Returns")
        self.assertEqual(quiz.before_answers_count, 2)
        self.assertEqual(quiz.before_correct_answers_count, 1)
        self.assertEqual(quiz.after_answers_count, 0)
        self.assertEqual(quiz.after_accuracy_percent, None)
        self.assertEqual(quiz.before_accuracy_percent, 50.0)

    def test_quiz_evidence_only_after_assignment(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row(
                        "q1",
                        is_correct=True,
                        finished_at="2026-09-16 10:00:00",
                    ),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 0)
        self.assertEqual(quiz.after_answers_count, 1)
        self.assertEqual(quiz.after_correct_answers_count, 1)
        self.assertEqual(quiz.after_accuracy_percent, 100.0)
        self.assertIsNone(quiz.before_accuracy_percent)

    def test_quiz_evidence_mixed_before_and_after(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row(
                        "q1",
                        is_correct=True,
                        finished_at="2026-09-10 10:00:00",
                    ),
                    _answer_row(
                        "q1",
                        is_correct=False,
                        finished_at="2026-09-16 10:00:00",
                    ),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 1)
        self.assertEqual(quiz.after_answers_count, 1)
        self.assertEqual(quiz.before_accuracy_percent, 100.0)
        self.assertEqual(quiz.after_accuracy_percent, 0.0)

    def test_quiz_evidence_exactly_at_deadline_counts_as_after(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row(
                        "q1",
                        is_correct=True,
                        finished_at=self.ASSIGNED_AT,
                    ),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 0)
        self.assertEqual(quiz.after_answers_count, 1)

    def test_quiz_evidence_ignores_unrelated_tags(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (
                _course(
                    "alpha",
                    quiz=_quiz(
                        _question("q1", ["Returns"]),
                        _question("q2", ["Customer"]),
                    ),
                ),
            )
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-10 10:00:00"),
                    _answer_row("q2", is_correct=False, finished_at="2026-09-10 11:00:00"),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 1)

    def test_quiz_evidence_tag_matching_is_case_insensitive(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", [" returns "]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-10 10:00:00"),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "RETURNS",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.tag, "RETURNS")
        self.assertEqual(quiz.before_answers_count, 1)

    def test_quiz_evidence_duplicate_matching_tags_count_once(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns", " returns "]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-10 10:00:00"),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 1)

    def test_quiz_evidence_skips_malformed_finished_at(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    {
                        "attempt_id": 1,
                        "question_id": "q1",
                        "is_correct": 1,
                        "finished_at": "not-a-timestamp",
                    },
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 0)
        self.assertEqual(quiz.after_answers_count, 0)

    def test_quiz_evidence_skips_unknown_question_id(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("missing", is_correct=True, finished_at="2026-09-10 10:00:00"),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "quiz",
            "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 0)

    def test_practical_evidence_only_before_assignment(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail",),
                reviewed_at="2026-09-10 10:00:00",
            ),
            FakeReviewFeedback(
                id=2,
                improvements=("Add detail",),
                reviewed_at="2026-09-14 11:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        self.assertIsNone(result.quiz)
        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.text, "Add detail")
        self.assertEqual(practical.before_evidence_count, 2)
        self.assertEqual(practical.after_evidence_count, 0)

    def test_practical_evidence_only_after_assignment(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail",),
                reviewed_at="2026-09-16 10:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 0)
        self.assertEqual(practical.after_evidence_count, 1)

    def test_practical_evidence_mixed_before_and_after(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail",),
                reviewed_at="2026-09-10 10:00:00",
            ),
            FakeReviewFeedback(
                id=2,
                improvements=("Add detail",),
                reviewed_at="2026-09-16 10:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 1)
        self.assertEqual(practical.after_evidence_count, 1)

    def test_practical_evidence_exactly_at_deadline_counts_as_after(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail",),
                reviewed_at=self.ASSIGNED_AT,
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 0)
        self.assertEqual(practical.after_evidence_count, 1)

    def test_practical_evidence_reason_matching_is_case_insensitive(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("  add   detail ",),
                reviewed_at="2026-09-10 10:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "ADD DETAIL",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.text, "ADD DETAIL")
        self.assertEqual(practical.before_evidence_count, 1)

    def test_practical_evidence_duplicate_improvement_in_one_attempt_counts_once(
        self,
    ) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail", "add detail"),
                reviewed_at="2026-09-10 10:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 1)

    def test_practical_evidence_ignores_unrelated_improvements(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Other issue",),
                reviewed_at="2026-09-10 10:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 0)
        self.assertEqual(practical.after_evidence_count, 0)

    def test_practical_evidence_ignores_strengths(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                strengths=("Add detail",),
                reviewed_at="2026-09-10 10:00:00",
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 0)

    def test_practical_evidence_skips_malformed_reviewed_at(self) -> None:
        self.practical_repository._reviewed_feedback = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail",),
                reviewed_at="not-a-timestamp",
            ),
            FakeReviewFeedback(
                id=2,
                improvements=("Add detail",),
                reviewed_at=None,
            ),
        ]

        result = self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 0)
        self.assertEqual(practical.after_evidence_count, 0)

    def test_rejects_invalid_development_source(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_development_impact_evidence(
                42,
                self.ASSIGNED_AT,
                "unknown",
                "Returns",
            )

    def test_rejects_blank_development_reason(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_development_impact_evidence(
                42,
                self.ASSIGNED_AT,
                "quiz",
                "   ",
            )

    def test_rejects_development_reason_over_200_characters(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_development_impact_evidence(
                42,
                self.ASSIGNED_AT,
                "quiz",
                "x" * 201,
            )

    def test_rejects_invalid_assigned_at(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_development_impact_evidence(
                42,
                "2026-99-99 25:00:00",
                "quiz",
                "Returns",
            )

    def test_rejects_invalid_user_id(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_development_impact_evidence(
                0,
                self.ASSIGNED_AT,
                "quiz",
                "Returns",
            )

    def test_practical_repository_called_with_canonical_user_id(self) -> None:
        self.service.get_development_impact_evidence(
            42,
            self.ASSIGNED_AT,
            "practical",
            "Add detail",
        )

        self.assertEqual(
            self.practical_repository.reviewed_feedback_calls,
            [(self.db_path, 42)],
        )

    def test_development_profile_behavior_unchanged(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _answer_row("q1", is_correct=False),
                    _answer_row("q1", is_correct=False),
                    _answer_row("q1", is_correct=False),
                ],
            }
        )
        practical_repository = FakePracticalTaskAttemptRepository()
        practical_repository._reviewed_feedback = [
            FakeReviewFeedback(id=1, improvements=("Add detail",)),
            FakeReviewFeedback(id=2, improvements=("Add detail",)),
        ]
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            practical_repository,
        )

        profile = service.get_development_profile(42)
        topics = service.get_quiz_topics_analytics(42)

        self.assertEqual(len(profile.quiz_development_areas), 1)
        self.assertEqual(profile.quiz_development_areas[0].tag, "Returns")
        self.assertEqual(len(profile.practical_development_areas), 1)
        self.assertEqual(topics.topics[0].answers_count, 3)


class _RowLikeAnswer:
    """Supports __getitem__ but not .get(), like sqlite3.Row."""

    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> object:
        return self._data[key]


class ManagerEmployeeDevelopmentImpactClassificationTests(unittest.TestCase):
    ASSIGNED_AT = "2026-09-15 12:00:00"

    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.practical_repository = FakePracticalTaskAttemptRepository()

    def _quiz_service(
        self,
        answers_by_course: dict[str, list],
    ) -> ManagerEmployeeAnalyticsService:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(answers_by_course)
        return ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

    def _practical_service(
        self,
        feedback_rows: list[FakeReviewFeedback],
    ) -> ManagerEmployeeAnalyticsService:
        self.practical_repository._reviewed_feedback = feedback_rows
        return ManagerEmployeeAnalyticsService(
            TopicAnalyticsFakeRuntime(()),
            TopicAnalyticsFakeQuizRepository({}),
            self.db_path,
            self.practical_repository,
        )

    def test_quiz_classification_improved(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    _answer_row("q1", is_correct=False, finished_at="2026-09-10 10:00:00"),
                    _answer_row("q1", is_correct=True, finished_at="2026-09-16 10:00:00"),
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)
        self.assertEqual(result.classification_label, "Есть улучшение")

    def test_quiz_classification_declined(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-10 10:00:00"),
                    _answer_row("q1", is_correct=False, finished_at="2026-09-16 10:00:00"),
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_DECLINED)
        self.assertEqual(result.classification_label, "Есть ухудшение")

    def test_quiz_classification_unchanged(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-10 10:00:00"),
                    _answer_row("q1", is_correct=False, finished_at="2026-09-10 11:00:00"),
                    _answer_row("q1", is_correct=True, finished_at="2026-09-16 10:00:00"),
                    _answer_row("q1", is_correct=False, finished_at="2026-09-16 11:00:00"),
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_UNCHANGED)
        self.assertEqual(result.classification_label, "Без заметного изменения")

    def test_quiz_classification_insufficient_data_only_before(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-10 10:00:00"),
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_INSUFFICIENT_DATA)
        self.assertEqual(result.classification_label, "Недостаточно данных")

    def test_quiz_classification_insufficient_data_only_after(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    _answer_row("q1", is_correct=True, finished_at="2026-09-16 10:00:00"),
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_INSUFFICIENT_DATA)

    def test_quiz_evidence_works_with_row_like_objects_without_get(self) -> None:
        runtime = TopicAnalyticsFakeRuntime(
            (_course("alpha", quiz=_quiz(_question("q1", ["Returns"]))),)
        )
        repository = TopicAnalyticsFakeQuizRepository(
            {
                "alpha": [
                    _RowLikeAnswer(
                        {
                            "attempt_id": 1,
                            "question_id": "q1",
                            "is_correct": 0,
                            "finished_at": "2026-09-10 10:00:00",
                        }
                    ),
                    _RowLikeAnswer(
                        {
                            "attempt_id": 2,
                            "question_id": "q1",
                            "is_correct": 1,
                            "finished_at": "2026-09-16 10:00:00",
                        }
                    ),
                ],
            }
        )
        service = ManagerEmployeeAnalyticsService(
            runtime,
            repository,
            self.db_path,
            self.practical_repository,
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 1)
        self.assertEqual(quiz.after_answers_count, 1)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)

    def test_quiz_malformed_timestamp_remains_ignored_for_classification(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    {
                        "attempt_id": 1,
                        "question_id": "q1",
                        "is_correct": 1,
                        "finished_at": "not-a-timestamp",
                    },
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_INSUFFICIENT_DATA)

    def test_practical_classification_improved_when_issue_decreases(self) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-10 10:00:00",
                ),
                FakeReviewFeedback(
                    id=2,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-14 11:00:00",
                ),
                FakeReviewFeedback(
                    id=3,
                    improvements=("Other issue",),
                    reviewed_at="2026-09-16 10:00:00",
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 2)
        self.assertEqual(practical.after_evidence_count, 0)
        self.assertEqual(practical.before_reviewed_attempts_count, 2)
        self.assertEqual(practical.after_reviewed_attempts_count, 1)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)

    def test_practical_classification_improved_when_issue_disappears(self) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-10 10:00:00",
                ),
                FakeReviewFeedback(
                    id=2,
                    improvements=("Other issue",),
                    reviewed_at="2026-09-16 10:00:00",
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.after_evidence_count, 0)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)

    def test_practical_classification_declined(self) -> None:
        feedback_rows = [
            FakeReviewFeedback(
                id=index,
                improvements=("Add detail",) if index <= 2 else ("Other issue",),
                reviewed_at=f"2026-09-{index:02d} 10:00:00",
            )
            for index in range(1, 11)
        ]
        feedback_rows.append(
            FakeReviewFeedback(
                id=11,
                improvements=("Add detail",),
                reviewed_at="2026-09-16 10:00:00",
            )
        )

        service = self._practical_service(feedback_rows)

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 2)
        self.assertEqual(practical.before_reviewed_attempts_count, 10)
        self.assertEqual(practical.after_evidence_count, 1)
        self.assertEqual(practical.after_reviewed_attempts_count, 1)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_DECLINED)

    def test_practical_classification_improved_when_rate_falls_despite_raw_count_rising(
        self,
    ) -> None:
        before_rows = [
            FakeReviewFeedback(
                id=index,
                improvements=("Add detail",),
                reviewed_at=f"2026-09-0{index} 10:00:00",
            )
            for index in (1, 2)
        ]
        after_rows = [
            FakeReviewFeedback(
                id=index,
                improvements=(
                    ("Add detail",)
                    if index in (11, 12, 13)
                    else ("Other issue",)
                ),
                reviewed_at=f"2026-09-{index - 10 + 15} 10:00:00",
            )
            for index in range(11, 21)
        ]

        service = self._practical_service(before_rows + after_rows)

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 2)
        self.assertEqual(practical.before_reviewed_attempts_count, 2)
        self.assertEqual(practical.after_evidence_count, 3)
        self.assertEqual(practical.after_reviewed_attempts_count, 10)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)

    def test_practical_classification_declined_when_rate_rises_despite_raw_count_falling(
        self,
    ) -> None:
        before_rows = [
            FakeReviewFeedback(
                id=index,
                improvements=(
                    ("Add detail",)
                    if index in (1, 2)
                    else ("Other issue",)
                ),
                reviewed_at=f"2026-09-{index:02d} 10:00:00",
            )
            for index in range(1, 11)
        ]
        after_rows = [
            FakeReviewFeedback(
                id=11,
                improvements=("Add detail",),
                reviewed_at="2026-09-16 10:00:00",
            ),
        ]

        service = self._practical_service(before_rows + after_rows)

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 2)
        self.assertEqual(practical.before_reviewed_attempts_count, 10)
        self.assertEqual(practical.after_evidence_count, 1)
        self.assertEqual(practical.after_reviewed_attempts_count, 1)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_DECLINED)

    def test_practical_classification_unchanged_when_rates_equal_despite_different_raw_counts(
        self,
    ) -> None:
        before_rows = [
            FakeReviewFeedback(
                id=1,
                improvements=("Add detail",),
                reviewed_at="2026-09-10 10:00:00",
            ),
            FakeReviewFeedback(
                id=2,
                improvements=("Other issue",),
                reviewed_at="2026-09-11 10:00:00",
            ),
        ]
        after_rows = [
            FakeReviewFeedback(
                id=index,
                improvements=(
                    ("Add detail",)
                    if index in (3, 4)
                    else ("Other issue",)
                ),
                reviewed_at=f"2026-09-{index + 13} 10:00:00",
            )
            for index in range(3, 7)
        ]

        service = self._practical_service(before_rows + after_rows)

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 1)
        self.assertEqual(practical.before_reviewed_attempts_count, 2)
        self.assertEqual(practical.after_evidence_count, 2)
        self.assertEqual(practical.after_reviewed_attempts_count, 4)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_UNCHANGED)

    def test_practical_classification_unchanged(self) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-10 10:00:00",
                ),
                FakeReviewFeedback(
                    id=2,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-16 10:00:00",
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_UNCHANGED)

    def test_practical_classification_insufficient_data_no_before_target(self) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Other issue",),
                    reviewed_at="2026-09-16 10:00:00",
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_INSUFFICIENT_DATA)

    def test_practical_classification_insufficient_data_no_after_reviewed_attempts(
        self,
    ) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-10 10:00:00",
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_evidence_count, 1)
        self.assertEqual(practical.after_reviewed_attempts_count, 0)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_INSUFFICIENT_DATA)

    def test_practical_unrelated_improvements_count_toward_reviewed_attempts(self) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-10 10:00:00",
                ),
                FakeReviewFeedback(
                    id=2,
                    improvements=("Other issue",),
                    reviewed_at="2026-09-16 10:00:00",
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_reviewed_attempts_count, 1)
        self.assertEqual(practical.after_reviewed_attempts_count, 1)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)

    def test_practical_malformed_reviewed_at_not_counted_as_reviewed(self) -> None:
        service = self._practical_service(
            [
                FakeReviewFeedback(
                    id=1,
                    improvements=("Add detail",),
                    reviewed_at="2026-09-10 10:00:00",
                ),
                FakeReviewFeedback(
                    id=2,
                    improvements=("Add detail",),
                    reviewed_at="not-a-timestamp",
                ),
                FakeReviewFeedback(
                    id=3,
                    improvements=("Other issue",),
                    reviewed_at=None,
                ),
            ]
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "practical", "Add detail",
        )

        practical = result.practical
        assert practical is not None
        self.assertEqual(practical.before_reviewed_attempts_count, 1)
        self.assertEqual(practical.after_reviewed_attempts_count, 0)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_INSUFFICIENT_DATA)

    def test_exact_at_deadline_remains_in_after_window_for_classification(self) -> None:
        service = self._quiz_service(
            {
                "alpha": [
                    _answer_row("q1", is_correct=False, finished_at="2026-09-10 10:00:00"),
                    _answer_row("q1", is_correct=True, finished_at=self.ASSIGNED_AT),
                ],
            }
        )

        result = service.get_development_impact_evidence(
            42, self.ASSIGNED_AT, "quiz", "Returns",
        )

        quiz = result.quiz
        assert quiz is not None
        self.assertEqual(quiz.before_answers_count, 1)
        self.assertEqual(quiz.after_answers_count, 1)
        self.assertEqual(result.classification, IMPACT_CLASSIFICATION_IMPROVED)


if __name__ == "__main__":
    unittest.main()
