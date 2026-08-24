"""Aggregate manager team analytics for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.web.manager_employee_analytics_service import (
    EmployeeQuizAnalytics,
    EmployeeQuizTopicsAnalytics,
    ManagerEmployeeAnalyticsService,
)
from app.web.manager_team_service import ManagerTeamMember, ManagerTeamService

DEVELOPMENT_TOPIC_ACCURACY_PERCENT = 70.0
MIN_TEAM_TOPIC_ANSWERS = 3


@dataclass(frozen=True)
class ManagerTeamTopicAnalytics:
    tag: str
    answers_count: int
    correct_answers_count: int
    accuracy_percent: float
    employees_count: int


@dataclass(frozen=True)
class ManagerTeamAnalytics:
    members_count: int
    started_members_count: int
    completed_members_count: int
    average_progress_percent: Optional[float]
    members_with_quiz_results_count: int
    members_requiring_attention_count: int
    members_without_quiz_data_count: int
    average_quiz_score_percent: Optional[float]
    development_topics: tuple[ManagerTeamTopicAnalytics, ...]


@dataclass(frozen=True)
class ManagerTeamMemberAnalytics:
    member: ManagerTeamMember
    quiz_analytics: EmployeeQuizAnalytics


@dataclass(frozen=True)
class ManagerTeamOverview:
    analytics: ManagerTeamAnalytics
    members: tuple[ManagerTeamMemberAnalytics, ...]


class ManagerTeamAnalyticsService:
    """Build aggregate analytics for one tenant-scoped manager team."""

    def __init__(
        self,
        team_service: ManagerTeamService,
        employee_analytics_service: ManagerEmployeeAnalyticsService,
    ) -> None:
        self._team_service = team_service
        self._employee_analytics_service = employee_analytics_service

    def get_team_overview(self, company_id: str) -> ManagerTeamOverview:
        members = self._team_service.get_team(company_id)

        if not members:
            return ManagerTeamOverview(
                analytics=_empty_team_analytics(),
                members=(),
            )

        member_rows: list[ManagerTeamMemberAnalytics] = []
        quiz_analytics_by_member: list[tuple[ManagerTeamMember, EmployeeQuizAnalytics]] = []
        topics_analytics_by_member: list[
            tuple[ManagerTeamMember, EmployeeQuizTopicsAnalytics]
        ] = []

        for member in members:
            quiz_analytics = self._employee_analytics_service.get_quiz_analytics(
                member.user_id
            )
            topics_analytics = (
                self._employee_analytics_service.get_quiz_topics_analytics(
                    member.user_id
                )
            )
            member_rows.append(
                ManagerTeamMemberAnalytics(
                    member=member,
                    quiz_analytics=quiz_analytics,
                )
            )
            quiz_analytics_by_member.append((member, quiz_analytics))
            topics_analytics_by_member.append((member, topics_analytics))

        analytics = _build_team_analytics(
            members,
            quiz_analytics_by_member,
            topics_analytics_by_member,
        )
        return ManagerTeamOverview(
            analytics=analytics,
            members=tuple(member_rows),
        )

    def get_team_analytics(self, company_id: str) -> ManagerTeamAnalytics:
        return self.get_team_overview(company_id).analytics


def _empty_team_analytics() -> ManagerTeamAnalytics:
    return ManagerTeamAnalytics(
        members_count=0,
        started_members_count=0,
        completed_members_count=0,
        average_progress_percent=None,
        members_with_quiz_results_count=0,
        members_requiring_attention_count=0,
        members_without_quiz_data_count=0,
        average_quiz_score_percent=None,
        development_topics=(),
    )


def _build_team_analytics(
    members: tuple[ManagerTeamMember, ...],
    quiz_analytics_by_member: list[tuple[ManagerTeamMember, EmployeeQuizAnalytics]],
    topics_analytics_by_member: list[
        tuple[ManagerTeamMember, EmployeeQuizTopicsAnalytics]
    ],
) -> ManagerTeamAnalytics:
    members_count = len(members)
    started_members_count = sum(
        member.started_courses_count > 0 for member in members
    )
    completed_members_count = sum(
        member.completed_courses_count > 0 for member in members
    )
    average_progress_percent = round(
        sum(member.average_progress_percent for member in members) / members_count,
        2,
    )

    members_with_quiz_results_count = 0
    members_requiring_attention_count = 0
    members_without_quiz_data_count = 0
    weighted_score_total = 0.0
    total_team_attempts = 0

    tag_stats: dict[str, dict[str, int]] = {}
    tag_employee_ids: dict[str, set[int]] = {}

    for member, quiz_analytics in quiz_analytics_by_member:
        if quiz_analytics.total_attempts_count > 0:
            members_with_quiz_results_count += 1
            if quiz_analytics.average_score_percent is not None:
                weighted_score_total += (
                    quiz_analytics.average_score_percent
                    * quiz_analytics.total_attempts_count
                )
                total_team_attempts += quiz_analytics.total_attempts_count
        else:
            members_without_quiz_data_count += 1

        if quiz_analytics.latest_failed_courses_count > 0:
            members_requiring_attention_count += 1

    for member, topics_analytics in topics_analytics_by_member:
        for topic in topics_analytics.topics:
            stats = tag_stats.setdefault(
                topic.tag,
                {"answers_count": 0, "correct_answers_count": 0},
            )
            stats["answers_count"] += topic.answers_count
            stats["correct_answers_count"] += topic.correct_answers_count
            tag_employee_ids.setdefault(topic.tag, set()).add(member.user_id)

    average_quiz_score_percent = (
        round(weighted_score_total / total_team_attempts, 2)
        if total_team_attempts
        else None
    )

    development_topics = tuple(
        _build_team_topic_analytics(
            tag,
            stats,
            len(tag_employee_ids[tag]),
        )
        for tag, stats in sorted(
            tag_stats.items(),
            key=lambda item: (
                _team_topic_accuracy_percent(item[1]),
                -item[1]["answers_count"],
                -len(tag_employee_ids[item[0]]),
                item[0].casefold(),
                item[0],
            ),
        )
        if stats["answers_count"] >= MIN_TEAM_TOPIC_ANSWERS
        and _team_topic_accuracy_percent(stats) < DEVELOPMENT_TOPIC_ACCURACY_PERCENT
    )

    return ManagerTeamAnalytics(
        members_count=members_count,
        started_members_count=started_members_count,
        completed_members_count=completed_members_count,
        average_progress_percent=average_progress_percent,
        members_with_quiz_results_count=members_with_quiz_results_count,
        members_requiring_attention_count=members_requiring_attention_count,
        members_without_quiz_data_count=members_without_quiz_data_count,
        average_quiz_score_percent=average_quiz_score_percent,
        development_topics=development_topics,
    )


def _team_topic_accuracy_percent(stats: dict[str, int]) -> float:
    answers_count = stats["answers_count"]
    if answers_count == 0:
        return 0.0
    return round(stats["correct_answers_count"] * 100 / answers_count, 2)


def _build_team_topic_analytics(
    tag: str,
    stats: dict[str, int],
    employees_count: int,
) -> ManagerTeamTopicAnalytics:
    return ManagerTeamTopicAnalytics(
        tag=tag,
        answers_count=stats["answers_count"],
        correct_answers_count=stats["correct_answers_count"],
        accuracy_percent=_team_topic_accuracy_percent(stats),
        employees_count=employees_count,
    )
