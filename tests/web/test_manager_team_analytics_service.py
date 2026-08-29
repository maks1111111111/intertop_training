"""Tests for aggregate manager team analytics."""

from __future__ import annotations

import unittest
from typing import Optional

from app.web.manager_employee_analytics_service import (
    EmployeePracticalSignalEvidence,
    EmployeePracticalSignalEvidenceSet,
    EmployeePracticalTaskAnalytics,
    EmployeeQuizAnalytics,
    EmployeeQuizTopicAnalytics,
    EmployeeQuizTopicsAnalytics,
    STRONG_TOPIC_ACCURACY_PERCENT,
)
from app.web.manager_team_analytics_service import (
    MIN_TEAM_PRACTICAL_SIGNAL_EMPLOYEES,
    ManagerTeamAnalyticsService,
    ManagerTeamMemberAnalytics,
    ManagerTeamPracticalSignal,
)
from app.web.manager_team_service import ManagerTeamMember


def _member(
    user_id: int,
    *,
    started: int = 1,
    completed: int = 0,
    progress: int = 50,
) -> ManagerTeamMember:
    return ManagerTeamMember(
        user_id=user_id,
        display_name=f"User {user_id}",
        username=f"user{user_id}",
        role="student",
        role_label="Сотрудник",
        started_courses_count=started,
        completed_courses_count=completed,
        average_progress_percent=progress,
    )


def _quiz_analytics(
    *,
    attempts: int = 0,
    average: Optional[float] = None,
    latest_failed: int = 0,
) -> EmployeeQuizAnalytics:
    return EmployeeQuizAnalytics(
        total_attempts_count=attempts,
        tested_courses_count=1 if attempts else 0,
        passed_courses_count=0,
        latest_failed_courses_count=latest_failed,
        best_score_percent=average,
        average_score_percent=average,
        courses=(),
    )


def _topics_analytics(
    *topics: EmployeeQuizTopicAnalytics,
) -> EmployeeQuizTopicsAnalytics:
    total = sum(topic.answers_count for topic in topics)
    return EmployeeQuizTopicsAnalytics(
        total_tagged_answers_count=total,
        topics=topics,
    )


def _practical_analytics(
    *,
    total: int = 0,
    reviewed: int = 0,
    passed: int = 0,
    failed: int = 0,
    pending: int = 0,
    scorable: int = 0,
    average: Optional[float] = None,
) -> EmployeePracticalTaskAnalytics:
    return EmployeePracticalTaskAnalytics(
        total_attempts_count=total,
        reviewed_attempts_count=reviewed,
        passed_attempts_count=passed,
        failed_attempts_count=failed,
        pending_attempts_count=pending,
        scorable_attempts_count=scorable,
        average_score_percent=average,
        best_score_percent=average,
        recent_attempts=(),
    )


def _practical_evidence(
    *,
    strengths=(),
    development_areas=(),
    reviewed_attempts_count: int = 0,
) -> EmployeePracticalSignalEvidenceSet:
    return EmployeePracticalSignalEvidenceSet(
        strengths=strengths,
        development_areas=development_areas,
        reviewed_attempts_count=reviewed_attempts_count,
    )


def _signal_evidence(text: str, count: int) -> EmployeePracticalSignalEvidence:
    return EmployeePracticalSignalEvidence(text=text, evidence_count=count)


class FakeTeamService:
    def __init__(self, members: tuple[ManagerTeamMember, ...]) -> None:
        self.members = members
        self.calls: list[str] = []

    def get_team(self, company_id: str) -> tuple[ManagerTeamMember, ...]:
        self.calls.append(company_id)
        return self.members


class FakeEmployeeAnalyticsService:
    def __init__(
        self,
        quiz_by_user: dict[int, EmployeeQuizAnalytics] | None = None,
        topics_by_user: dict[int, EmployeeQuizTopicsAnalytics] | None = None,
        practical_by_user: dict[int, EmployeePracticalTaskAnalytics] | None = None,
        practical_evidence_by_user: dict[
            int, EmployeePracticalSignalEvidenceSet
        ] | None = None,
    ) -> None:
        self.quiz_by_user = quiz_by_user or {}
        self.topics_by_user = topics_by_user or {}
        self.practical_by_user = practical_by_user or {}
        self.practical_evidence_by_user = practical_evidence_by_user or {}
        self.quiz_calls: list[int] = []
        self.topics_calls: list[int] = []
        self.practical_calls: list[int] = []
        self.practical_evidence_calls: list[int] = []

    def get_quiz_analytics(self, user_id: int) -> EmployeeQuizAnalytics:
        self.quiz_calls.append(user_id)
        return self.quiz_by_user.get(user_id, _quiz_analytics())

    def get_quiz_topics_analytics(self, user_id: int) -> EmployeeQuizTopicsAnalytics:
        self.topics_calls.append(user_id)
        return self.topics_by_user.get(user_id, _topics_analytics())

    def get_practical_task_analytics(
        self,
        user_id: int,
        limit: int = 10,
    ) -> EmployeePracticalTaskAnalytics:
        self.practical_calls.append(user_id)
        return self.practical_by_user.get(user_id, _practical_analytics())

    def get_practical_signal_evidence(
        self,
        user_id: int,
    ) -> EmployeePracticalSignalEvidenceSet:
        self.practical_evidence_calls.append(user_id)
        return self.practical_evidence_by_user.get(
            user_id,
            _practical_evidence(),
        )


class ManagerTeamAnalyticsServiceTests(unittest.TestCase):
    def test_empty_team_returns_zero_counts(self) -> None:
        team_service = FakeTeamService(())
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.members_count, 0)
        self.assertEqual(result.started_members_count, 0)
        self.assertEqual(result.completed_members_count, 0)
        self.assertIsNone(result.average_progress_percent)
        self.assertEqual(result.members_with_quiz_results_count, 0)
        self.assertEqual(result.members_requiring_attention_count, 0)
        self.assertEqual(result.members_without_quiz_data_count, 0)
        self.assertIsNone(result.average_quiz_score_percent)
        self.assertEqual(result.strengths_topics, ())
        self.assertEqual(result.development_topics, ())
        self.assertEqual(result.members_with_practical_attempts_count, 0)
        self.assertEqual(result.members_with_pending_practical_tasks_count, 0)
        self.assertEqual(result.members_with_failed_practical_tasks_count, 0)
        self.assertEqual(result.practical_attempts_count, 0)
        self.assertEqual(result.practical_reviewed_attempts_count, 0)
        self.assertEqual(result.practical_passed_attempts_count, 0)
        self.assertEqual(result.practical_failed_attempts_count, 0)
        self.assertEqual(result.practical_pending_attempts_count, 0)
        self.assertIsNone(result.average_practical_score_percent)
        self.assertEqual(result.practical_strengths, ())
        self.assertEqual(result.practical_development_areas, ())
        self.assertEqual(result.reviewed_practical_attempts_count, 0)
        self.assertEqual(team_service.calls, ["company-a"])
        self.assertEqual(employee_service.quiz_calls, [])
        self.assertEqual(employee_service.topics_calls, [])
        self.assertEqual(employee_service.practical_calls, [])
        self.assertEqual(employee_service.practical_evidence_calls, [])

    def test_aggregate_counts_and_averages(self) -> None:
        members = (
            _member(1, started=2, completed=1, progress=80),
            _member(2, started=0, completed=0, progress=40),
            _member(3, started=1, completed=1, progress=60),
        )
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            quiz_by_user={
                1: _quiz_analytics(attempts=4, average=80.0),
                2: _quiz_analytics(attempts=0),
                3: _quiz_analytics(attempts=2, average=60.0, latest_failed=1),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.members_count, 3)
        self.assertEqual(result.started_members_count, 2)
        self.assertEqual(result.completed_members_count, 2)
        self.assertAlmostEqual(result.average_progress_percent, 60.0)
        self.assertEqual(result.members_with_quiz_results_count, 2)
        self.assertEqual(result.members_requiring_attention_count, 1)
        self.assertEqual(result.members_without_quiz_data_count, 1)

    def test_weighted_team_quiz_average(self) -> None:
        members = (
            _member(1, progress=50),
            _member(2, progress=50),
        )
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            quiz_by_user={
                1: _quiz_analytics(attempts=4, average=80.0),
                2: _quiz_analytics(attempts=2, average=50.0),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        # (80*4 + 50*2) / 6 = 420/6 = 70.0
        self.assertAlmostEqual(result.average_quiz_score_percent, 70.0)

    def test_quiz_attempts_without_average_do_not_break_team_average(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            quiz_by_user={
                1: _quiz_analytics(attempts=2, average=None),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.members_with_quiz_results_count, 1)
        self.assertIsNone(result.average_quiz_score_percent)

    def test_no_quiz_attempts_yields_none_average(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertIsNone(result.average_quiz_score_percent)
        self.assertEqual(result.members_without_quiz_data_count, 2)
        self.assertEqual(result.members_with_quiz_results_count, 0)

    def test_attention_count(self) -> None:
        members = (_member(1), _member(2), _member(3))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            quiz_by_user={
                1: _quiz_analytics(attempts=1, average=90.0, latest_failed=1),
                2: _quiz_analytics(attempts=1, average=90.0, latest_failed=1),
                3: _quiz_analytics(attempts=1, average=90.0, latest_failed=0),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.members_requiring_attention_count, 2)

    def test_topic_aggregation_across_multiple_employees(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Возвраты",
                        answers_count=2,
                        correct_answers_count=1,
                        accuracy_percent=50.0,
                    ),
                ),
                2: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Возвраты",
                        answers_count=2,
                        correct_answers_count=0,
                        accuracy_percent=0.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.development_topics), 1)
        topic = result.development_topics[0]
        self.assertEqual(topic.tag, "Возвраты")
        self.assertEqual(topic.answers_count, 4)
        self.assertEqual(topic.correct_answers_count, 1)
        self.assertAlmostEqual(topic.accuracy_percent, 25.0)
        self.assertEqual(topic.employees_count, 2)

    def test_employees_count_per_topic(self) -> None:
        members = (_member(1), _member(2), _member(3))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Сервис",
                        answers_count=3,
                        correct_answers_count=1,
                        accuracy_percent=33.33,
                    ),
                ),
                2: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Сервис",
                        answers_count=3,
                        correct_answers_count=1,
                        accuracy_percent=33.33,
                    ),
                ),
                3: _topics_analytics(),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.development_topics), 1)
        self.assertEqual(result.development_topics[0].employees_count, 2)

    def test_topic_below_70_percent_included(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Слабая тема",
                        answers_count=3,
                        correct_answers_count=2,
                        accuracy_percent=66.67,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.development_topics), 1)
        self.assertEqual(result.development_topics[0].tag, "Слабая тема")

    def test_exactly_70_percent_excluded(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Граница",
                        answers_count=10,
                        correct_answers_count=7,
                        accuracy_percent=70.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.development_topics, ())

    def test_topic_with_fewer_than_three_answers_excluded(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Мало данных",
                        answers_count=2,
                        correct_answers_count=0,
                        accuracy_percent=0.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.development_topics, ())

    def test_deterministic_topic_ordering(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Beta",
                        answers_count=3,
                        correct_answers_count=1,
                        accuracy_percent=33.33,
                    ),
                    EmployeeQuizTopicAnalytics(
                        tag="Alpha",
                        answers_count=5,
                        correct_answers_count=2,
                        accuracy_percent=40.0,
                    ),
                ),
                2: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Gamma",
                        answers_count=4,
                        correct_answers_count=1,
                        accuracy_percent=25.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(
            tuple(topic.tag for topic in result.development_topics),
            ("Gamma", "Beta", "Alpha"),
        )

    def test_employee_analytics_called_only_for_returned_members(self) -> None:
        members = (_member(10), _member(20))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        service.get_team_analytics("company-a")

        self.assertEqual(employee_service.quiz_calls, [10, 20])
        self.assertEqual(employee_service.topics_calls, [10, 20])
        self.assertEqual(employee_service.practical_calls, [10, 20])
        self.assertEqual(employee_service.practical_evidence_calls, [10, 20])

    def test_team_service_called_exactly_once(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        service.get_team_analytics("  company-a  ")

        self.assertEqual(team_service.calls, ["  company-a  "])

    def test_get_team_overview_fetches_team_once(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            quiz_by_user={
                1: _quiz_analytics(attempts=2, average=80.0),
                2: _quiz_analytics(attempts=1, average=60.0),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        overview = service.get_team_overview("company-a")

        self.assertEqual(team_service.calls, ["company-a"])
        self.assertEqual(employee_service.quiz_calls, [1, 2])
        self.assertEqual(employee_service.topics_calls, [1, 2])
        self.assertEqual(employee_service.practical_calls, [1, 2])
        self.assertEqual(employee_service.practical_evidence_calls, [1, 2])
        self.assertEqual(len(overview.members), 2)

    def test_get_team_overview_member_rows_contain_quiz_analytics(self) -> None:
        members = (_member(10),)
        quiz = _quiz_analytics(attempts=3, average=75.0, latest_failed=1)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(quiz_by_user={10: quiz})
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        overview = service.get_team_overview("company-a")

        self.assertEqual(len(overview.members), 1)
        row = overview.members[0]
        self.assertIsInstance(row, ManagerTeamMemberAnalytics)
        self.assertEqual(row.member.user_id, 10)
        self.assertEqual(row.quiz_analytics, quiz)

    def test_get_team_overview_aggregate_matches_get_team_analytics(self) -> None:
        members = (
            _member(1, started=2, completed=1, progress=80),
            _member(2, started=0, completed=0, progress=40),
        )
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            quiz_by_user={
                1: _quiz_analytics(attempts=4, average=80.0),
                2: _quiz_analytics(attempts=0),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        overview = service.get_team_overview("company-a")
        direct = service.get_team_analytics("company-a")

        self.assertEqual(overview.analytics, direct)
        self.assertEqual(overview.analytics.members_count, 2)
        self.assertAlmostEqual(overview.analytics.average_progress_percent, 60.0)

    def test_get_team_overview_empty_team_performs_no_employee_analytics(self) -> None:
        team_service = FakeTeamService(())
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        overview = service.get_team_overview("company-a")

        self.assertEqual(overview.members, ())
        self.assertEqual(overview.analytics.members_count, 0)
        self.assertEqual(employee_service.quiz_calls, [])
        self.assertEqual(employee_service.topics_calls, [])
        self.assertEqual(employee_service.practical_calls, [])
        self.assertEqual(employee_service.practical_evidence_calls, [])

    def test_get_team_analytics_delegates_to_overview(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(team_service.calls, ["company-a"])
        self.assertEqual(employee_service.quiz_calls, [1])
        self.assertEqual(employee_service.practical_calls, [1])
        self.assertEqual(result.members_count, 1)

    def test_aggregates_practical_counts_across_multiple_employees(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_by_user={
                1: _practical_analytics(
                    total=3,
                    reviewed=2,
                    passed=1,
                    failed=1,
                    pending=1,
                    scorable=2,
                    average=70.0,
                ),
                2: _practical_analytics(
                    total=1,
                    reviewed=1,
                    passed=1,
                    failed=0,
                    pending=0,
                    scorable=1,
                    average=90.0,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.members_with_practical_attempts_count, 2)
        self.assertEqual(result.members_with_pending_practical_tasks_count, 1)
        self.assertEqual(result.members_with_failed_practical_tasks_count, 1)
        self.assertEqual(result.practical_attempts_count, 4)
        self.assertEqual(result.practical_reviewed_attempts_count, 3)
        self.assertEqual(result.practical_passed_attempts_count, 2)
        self.assertEqual(result.practical_failed_attempts_count, 1)
        self.assertEqual(result.practical_pending_attempts_count, 1)

    def test_weighted_practical_average_uses_scorable_attempt_count(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_by_user={
                1: _practical_analytics(
                    total=2,
                    reviewed=2,
                    passed=2,
                    scorable=2,
                    average=80.0,
                ),
                2: _practical_analytics(
                    total=8,
                    reviewed=8,
                    passed=8,
                    scorable=8,
                    average=50.0,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        # (80*2 + 50*8) / 10 = 56.0
        self.assertAlmostEqual(result.average_practical_score_percent, 56.0)

    def test_no_practical_attempts_yields_none_average(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertIsNone(result.average_practical_score_percent)
        self.assertEqual(result.members_with_practical_attempts_count, 0)

    def test_get_team_overview_member_rows_contain_practical_analytics(self) -> None:
        members = (_member(10),)
        practical = _practical_analytics(total=2, reviewed=2, scorable=2, average=75.0)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_by_user={10: practical},
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        overview = service.get_team_overview("company-a")

        self.assertEqual(len(overview.members), 1)
        row = overview.members[0]
        self.assertEqual(row.practical_task_analytics, practical)

    def test_practical_analytics_called_once_per_member(self) -> None:
        members = (_member(1), _member(2), _member(3))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        service.get_team_overview("company-a")

        self.assertEqual(employee_service.practical_calls, [1, 2, 3])
        self.assertEqual(len(employee_service.practical_calls), 3)
        self.assertEqual(employee_service.practical_evidence_calls, [1, 2, 3])

    def test_strength_topic_at_least_80_percent_included(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Сервис",
                        answers_count=4,
                        correct_answers_count=4,
                        accuracy_percent=100.0,
                    ),
                ),
                2: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Сервис",
                        answers_count=4,
                        correct_answers_count=3,
                        accuracy_percent=75.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.strengths_topics), 1)
        topic = result.strengths_topics[0]
        self.assertEqual(topic.tag, "Сервис")
        self.assertAlmostEqual(topic.accuracy_percent, 87.5)
        self.assertEqual(topic.employees_count, 2)

    def test_exactly_80_percent_included_as_strength(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Граница",
                        answers_count=5,
                        correct_answers_count=4,
                        accuracy_percent=80.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.strengths_topics), 1)
        self.assertEqual(result.strengths_topics[0].tag, "Граница")

    def test_neutral_topic_excluded_from_strength_and_development(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Нейтральная",
                        answers_count=10,
                        correct_answers_count=7,
                        accuracy_percent=70.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.strengths_topics, ())
        self.assertEqual(result.development_topics, ())

    def test_strength_topic_ordering(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            topics_by_user={
                1: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Beta",
                        answers_count=3,
                        correct_answers_count=3,
                        accuracy_percent=100.0,
                    ),
                    EmployeeQuizTopicAnalytics(
                        tag="Alpha",
                        answers_count=5,
                        correct_answers_count=4,
                        accuracy_percent=80.0,
                    ),
                ),
                2: _topics_analytics(
                    EmployeeQuizTopicAnalytics(
                        tag="Gamma",
                        answers_count=4,
                        correct_answers_count=4,
                        accuracy_percent=100.0,
                    ),
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(
            tuple(topic.tag for topic in result.strengths_topics),
            ("Gamma", "Beta", "Alpha"),
        )

    def test_team_practical_signal_qualifies_with_two_employees(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_evidence_by_user={
                1: _practical_evidence(
                    strengths=(_signal_evidence("Clear communication", 1),),
                    reviewed_attempts_count=1,
                ),
                2: _practical_evidence(
                    strengths=(_signal_evidence("Clear communication", 1),),
                    reviewed_attempts_count=1,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.practical_strengths), 1)
        signal = result.practical_strengths[0]
        self.assertEqual(signal.text, "Clear communication")
        self.assertEqual(signal.evidence_count, 2)
        self.assertEqual(signal.employees_count, 2)

    def test_team_practical_signal_from_one_employee_does_not_qualify(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_evidence_by_user={
                1: _practical_evidence(
                    strengths=(_signal_evidence("Only one employee", 5),),
                    reviewed_attempts_count=5,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.practical_strengths, ())

    def test_team_practical_signal_sums_evidence_across_employees(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_evidence_by_user={
                1: _practical_evidence(
                    development_areas=(_signal_evidence("Add detail", 2),),
                    reviewed_attempts_count=2,
                ),
                2: _practical_evidence(
                    development_areas=(_signal_evidence("Add detail", 3),),
                    reviewed_attempts_count=3,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.practical_development_areas), 1)
        signal = result.practical_development_areas[0]
        self.assertEqual(signal.evidence_count, 5)
        self.assertEqual(signal.employees_count, 2)

    def test_team_practical_signals_merge_case_insensitively(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_evidence_by_user={
                1: _practical_evidence(
                    strengths=(_signal_evidence("Clear communication", 1),),
                    reviewed_attempts_count=1,
                ),
                2: _practical_evidence(
                    strengths=(_signal_evidence("clear communication", 1),),
                    reviewed_attempts_count=1,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(len(result.practical_strengths), 1)
        self.assertEqual(result.practical_strengths[0].evidence_count, 2)

    def test_team_practical_signals_sorted_deterministically(self) -> None:
        members = (_member(1), _member(2), _member(3))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_evidence_by_user={
                1: _practical_evidence(
                    strengths=(
                        _signal_evidence("Beta signal", 1),
                        _signal_evidence("Alpha signal", 1),
                    ),
                    reviewed_attempts_count=1,
                ),
                2: _practical_evidence(
                    strengths=(_signal_evidence("Beta signal", 1),),
                    reviewed_attempts_count=1,
                ),
                3: _practical_evidence(
                    strengths=(_signal_evidence("Alpha signal", 1),),
                    reviewed_attempts_count=1,
                ),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(
            [signal.text for signal in result.practical_strengths],
            ["Alpha signal", "Beta signal"],
        )

    def test_reviewed_practical_attempts_count_aggregated(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService(
            practical_evidence_by_user={
                1: _practical_evidence(reviewed_attempts_count=2),
                2: _practical_evidence(reviewed_attempts_count=3),
            },
        )
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(result.reviewed_practical_attempts_count, 5)

    def test_practical_evidence_called_once_per_member(self) -> None:
        members = (_member(1), _member(2))
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        service.get_team_overview("company-a")

        self.assertEqual(employee_service.practical_evidence_calls, [1, 2])

    def test_team_constants_match_requirements(self) -> None:
        self.assertEqual(MIN_TEAM_PRACTICAL_SIGNAL_EMPLOYEES, 2)
        self.assertEqual(STRONG_TOPIC_ACCURACY_PERCENT, 80.0)


if __name__ == "__main__":
    unittest.main()
