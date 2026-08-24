"""Tests for aggregate manager team analytics."""

from __future__ import annotations

import unittest
from typing import Optional

from app.web.manager_employee_analytics_service import (
    EmployeeQuizAnalytics,
    EmployeeQuizTopicAnalytics,
    EmployeeQuizTopicsAnalytics,
)
from app.web.manager_team_analytics_service import (
    ManagerTeamAnalyticsService,
    ManagerTeamMemberAnalytics,
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
    ) -> None:
        self.quiz_by_user = quiz_by_user or {}
        self.topics_by_user = topics_by_user or {}
        self.quiz_calls: list[int] = []
        self.topics_calls: list[int] = []

    def get_quiz_analytics(self, user_id: int) -> EmployeeQuizAnalytics:
        self.quiz_calls.append(user_id)
        return self.quiz_by_user.get(user_id, _quiz_analytics())

    def get_quiz_topics_analytics(self, user_id: int) -> EmployeeQuizTopicsAnalytics:
        self.topics_calls.append(user_id)
        return self.topics_by_user.get(user_id, _topics_analytics())


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
        self.assertEqual(result.development_topics, ())
        self.assertEqual(team_service.calls, ["company-a"])
        self.assertEqual(employee_service.quiz_calls, [])
        self.assertEqual(employee_service.topics_calls, [])

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

    def test_get_team_analytics_delegates_to_overview(self) -> None:
        members = (_member(1),)
        team_service = FakeTeamService(members)
        employee_service = FakeEmployeeAnalyticsService()
        service = ManagerTeamAnalyticsService(team_service, employee_service)

        result = service.get_team_analytics("company-a")

        self.assertEqual(team_service.calls, ["company-a"])
        self.assertEqual(employee_service.quiz_calls, [1])
        self.assertEqual(result.members_count, 1)


if __name__ == "__main__":
    unittest.main()
