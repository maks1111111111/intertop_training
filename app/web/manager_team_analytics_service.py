"""Aggregate manager team analytics for the Web UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from app.web.manager_employee_analytics_service import (
    EmployeePracticalTaskAnalytics,
    EmployeePracticalSignalEvidenceSet,
    EmployeeQuizAnalytics,
    EmployeeQuizTopicsAnalytics,
    ManagerEmployeeAnalyticsService,
    STRONG_TOPIC_ACCURACY_PERCENT,
)
from app.web.manager_team_service import ManagerTeamMember, ManagerTeamService

DEVELOPMENT_TOPIC_ACCURACY_PERCENT = 70.0
MIN_TEAM_TOPIC_ANSWERS = 3
MIN_TEAM_PRACTICAL_SIGNAL_EMPLOYEES = 2


@dataclass(frozen=True)
class ManagerTeamTopicAnalytics:
    tag: str
    answers_count: int
    correct_answers_count: int
    accuracy_percent: float
    employees_count: int


@dataclass(frozen=True)
class ManagerTeamPracticalSignal:
    text: str
    evidence_count: int
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
    strengths_topics: tuple[ManagerTeamTopicAnalytics, ...]
    development_topics: tuple[ManagerTeamTopicAnalytics, ...]
    members_with_practical_attempts_count: int
    members_with_pending_practical_tasks_count: int
    members_with_failed_practical_tasks_count: int
    practical_attempts_count: int
    practical_reviewed_attempts_count: int
    practical_passed_attempts_count: int
    practical_failed_attempts_count: int
    practical_pending_attempts_count: int
    average_practical_score_percent: Optional[float]
    practical_strengths: tuple[ManagerTeamPracticalSignal, ...]
    practical_development_areas: tuple[ManagerTeamPracticalSignal, ...]
    reviewed_practical_attempts_count: int


@dataclass(frozen=True)
class ManagerTeamMemberAnalytics:
    member: ManagerTeamMember
    quiz_analytics: EmployeeQuizAnalytics
    practical_task_analytics: EmployeePracticalTaskAnalytics
    topics_analytics: EmployeeQuizTopicsAnalytics
    practical_signal_evidence: EmployeePracticalSignalEvidenceSet


@dataclass(frozen=True)
class ManagerActionRecommendation:
    code: str
    priority: str
    title: str
    description: str
    affected_employees_count: int
    affected_user_ids: tuple[int, ...]
    target_url: Optional[str] = None


@dataclass(frozen=True)
class ManagerRecommendationDevelopmentAction:
    kind: str
    title: str
    description: str
    url: str


@dataclass(frozen=True)
class ManagerRecommendationAffectedMember:
    user_id: int
    display_name: str
    username: Optional[str]
    reason: str
    profile_url: str
    development_actions: tuple[ManagerRecommendationDevelopmentAction, ...] = ()


@dataclass(frozen=True)
class ManagerRecommendationDetail:
    recommendation: ManagerActionRecommendation
    members: tuple[ManagerRecommendationAffectedMember, ...]


@dataclass(frozen=True)
class ManagerTeamOverview:
    analytics: ManagerTeamAnalytics
    members: tuple[ManagerTeamMemberAnalytics, ...]
    recommendations: tuple[ManagerActionRecommendation, ...]


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
                recommendations=(),
            )

        member_rows: list[ManagerTeamMemberAnalytics] = []
        quiz_analytics_by_member: list[tuple[ManagerTeamMember, EmployeeQuizAnalytics]] = []
        topics_analytics_by_member: list[
            tuple[ManagerTeamMember, EmployeeQuizTopicsAnalytics]
        ] = []
        practical_analytics_by_member: list[
            tuple[ManagerTeamMember, EmployeePracticalTaskAnalytics]
        ] = []
        practical_evidence_by_member: list[
            tuple[ManagerTeamMember, EmployeePracticalSignalEvidenceSet]
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
            practical_task_analytics = (
                self._employee_analytics_service.get_practical_task_analytics(
                    member.user_id
                )
            )
            practical_signal_evidence = (
                self._employee_analytics_service.get_practical_signal_evidence(
                    member.user_id
                )
            )
            member_rows.append(
                ManagerTeamMemberAnalytics(
                    member=member,
                    quiz_analytics=quiz_analytics,
                    practical_task_analytics=practical_task_analytics,
                    topics_analytics=topics_analytics,
                    practical_signal_evidence=practical_signal_evidence,
                )
            )
            quiz_analytics_by_member.append((member, quiz_analytics))
            topics_analytics_by_member.append((member, topics_analytics))
            practical_analytics_by_member.append(
                (member, practical_task_analytics)
            )
            practical_evidence_by_member.append(
                (member, practical_signal_evidence)
            )

        analytics = _build_team_analytics(
            members,
            quiz_analytics_by_member,
            topics_analytics_by_member,
            practical_analytics_by_member,
            practical_evidence_by_member,
        )
        member_rows_tuple = tuple(member_rows)
        recommendations = _build_team_recommendations(analytics, member_rows_tuple)
        return ManagerTeamOverview(
            analytics=analytics,
            members=member_rows_tuple,
            recommendations=recommendations,
        )

    def get_team_analytics(self, company_id: str) -> ManagerTeamAnalytics:
        return self.get_team_overview(company_id).analytics

    def get_recommendation_detail(
        self,
        company_id: str,
        recommendation_code: str,
    ) -> Optional[ManagerRecommendationDetail]:
        overview = self.get_team_overview(company_id)
        recommendation = next(
            (
                item
                for item in overview.recommendations
                if item.code == recommendation_code
            ),
            None,
        )
        if recommendation is None:
            return None

        members_by_id = {
            row.member.user_id: row for row in overview.members
        }
        affected_members: list[ManagerRecommendationAffectedMember] = []
        for user_id in recommendation.affected_user_ids:
            row = members_by_id.get(user_id)
            if row is None:
                continue
            affected_members.append(
                ManagerRecommendationAffectedMember(
                    user_id=user_id,
                    display_name=row.member.display_name,
                    username=row.member.username,
                    reason=_member_recommendation_reason(
                        recommendation,
                        row,
                        overview.analytics,
                    ),
                    profile_url=f"/manager/team/{user_id}",
                    development_actions=_member_recommendation_development_actions(
                        recommendation,
                        row,
                    ),
                )
            )

        return ManagerRecommendationDetail(
            recommendation=recommendation,
            members=tuple(affected_members),
        )


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
        strengths_topics=(),
        development_topics=(),
        members_with_practical_attempts_count=0,
        members_with_pending_practical_tasks_count=0,
        members_with_failed_practical_tasks_count=0,
        practical_attempts_count=0,
        practical_reviewed_attempts_count=0,
        practical_passed_attempts_count=0,
        practical_failed_attempts_count=0,
        practical_pending_attempts_count=0,
        average_practical_score_percent=None,
        practical_strengths=(),
        practical_development_areas=(),
        reviewed_practical_attempts_count=0,
    )


def _build_team_analytics(
    members: tuple[ManagerTeamMember, ...],
    quiz_analytics_by_member: list[tuple[ManagerTeamMember, EmployeeQuizAnalytics]],
    topics_analytics_by_member: list[
        tuple[ManagerTeamMember, EmployeeQuizTopicsAnalytics]
    ],
    practical_analytics_by_member: list[
        tuple[ManagerTeamMember, EmployeePracticalTaskAnalytics]
    ],
    practical_evidence_by_member: list[
        tuple[ManagerTeamMember, EmployeePracticalSignalEvidenceSet]
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

    members_with_practical_attempts_count = 0
    members_with_pending_practical_tasks_count = 0
    members_with_failed_practical_tasks_count = 0
    practical_attempts_count = 0
    practical_reviewed_attempts_count = 0
    practical_passed_attempts_count = 0
    practical_failed_attempts_count = 0
    practical_pending_attempts_count = 0
    practical_weighted_score_total = 0.0
    total_scorable_practical_attempts = 0

    for _member, practical_analytics in practical_analytics_by_member:
        if practical_analytics.total_attempts_count > 0:
            members_with_practical_attempts_count += 1
        if practical_analytics.pending_attempts_count > 0:
            members_with_pending_practical_tasks_count += 1
        if practical_analytics.failed_attempts_count > 0:
            members_with_failed_practical_tasks_count += 1

        practical_attempts_count += practical_analytics.total_attempts_count
        practical_reviewed_attempts_count += (
            practical_analytics.reviewed_attempts_count
        )
        practical_passed_attempts_count += practical_analytics.passed_attempts_count
        practical_failed_attempts_count += practical_analytics.failed_attempts_count
        practical_pending_attempts_count += practical_analytics.pending_attempts_count

        if (
            practical_analytics.average_score_percent is not None
            and practical_analytics.scorable_attempts_count > 0
        ):
            practical_weighted_score_total += (
                practical_analytics.average_score_percent
                * practical_analytics.scorable_attempts_count
            )
            total_scorable_practical_attempts += (
                practical_analytics.scorable_attempts_count
            )

    average_practical_score_percent = (
        round(
            practical_weighted_score_total / total_scorable_practical_attempts,
            2,
        )
        if total_scorable_practical_attempts
        else None
    )

    reviewed_practical_attempts_count = sum(
        evidence.reviewed_attempts_count
        for _member, evidence in practical_evidence_by_member
    )

    strengths_topics = tuple(
        _build_team_topic_analytics(
            tag,
            stats,
            len(tag_employee_ids[tag]),
        )
        for tag, stats in sorted(
            tag_stats.items(),
            key=lambda item: (
                -_team_topic_accuracy_percent(item[1]),
                -item[1]["answers_count"],
                -len(tag_employee_ids[item[0]]),
                item[0].casefold(),
                item[0],
            ),
        )
        if stats["answers_count"] >= MIN_TEAM_TOPIC_ANSWERS
        and _team_topic_accuracy_percent(stats) >= STRONG_TOPIC_ACCURACY_PERCENT
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

    practical_strengths, practical_development_areas = (
        _aggregate_team_practical_signals(practical_evidence_by_member)
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
        strengths_topics=strengths_topics,
        development_topics=development_topics,
        members_with_practical_attempts_count=members_with_practical_attempts_count,
        members_with_pending_practical_tasks_count=(
            members_with_pending_practical_tasks_count
        ),
        members_with_failed_practical_tasks_count=(
            members_with_failed_practical_tasks_count
        ),
        practical_attempts_count=practical_attempts_count,
        practical_reviewed_attempts_count=practical_reviewed_attempts_count,
        practical_passed_attempts_count=practical_passed_attempts_count,
        practical_failed_attempts_count=practical_failed_attempts_count,
        practical_pending_attempts_count=practical_pending_attempts_count,
        average_practical_score_percent=average_practical_score_percent,
        practical_strengths=practical_strengths,
        practical_development_areas=practical_development_areas,
        reviewed_practical_attempts_count=reviewed_practical_attempts_count,
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


def _aggregate_team_practical_signals(
    practical_evidence_by_member: list[
        tuple[ManagerTeamMember, EmployeePracticalSignalEvidenceSet]
    ],
) -> tuple[
    tuple[ManagerTeamPracticalSignal, ...],
    tuple[ManagerTeamPracticalSignal, ...],
]:
    strength_stats: dict[str, dict[str, object]] = {}
    development_stats: dict[str, dict[str, object]] = {}

    for member, evidence in practical_evidence_by_member:
        _merge_employee_practical_signals(
            strength_stats,
            evidence.strengths,
            member.user_id,
        )
        _merge_employee_practical_signals(
            development_stats,
            evidence.development_areas,
            member.user_id,
        )

    return (
        _qualifying_team_practical_signals(strength_stats),
        _qualifying_team_practical_signals(development_stats),
    )


def _merge_employee_practical_signals(
    aggregated: dict[str, dict[str, object]],
    signals,
    user_id: int,
) -> None:
    for signal in signals:
        signal_key = signal.text.casefold()
        if signal_key not in aggregated:
            aggregated[signal_key] = {
                "display": signal.text,
                "evidence_count": 0,
                "employee_ids": set(),
            }
        aggregated[signal_key]["evidence_count"] = (
            int(aggregated[signal_key]["evidence_count"]) + signal.evidence_count
        )
        employee_ids = aggregated[signal_key]["employee_ids"]
        assert isinstance(employee_ids, set)
        employee_ids.add(user_id)


def _recommendation_priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}[priority]


def _safe_recommendation_code_fragment(text: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold().strip())
    slug = slug.strip("-")
    return slug or fallback


def _recommendation_target_url(code: str) -> str:
    return f"/manager/team/recommendation?code={quote(code, safe='')}"


def _sorted_user_ids(user_ids) -> tuple[int, ...]:
    return tuple(sorted(set(user_ids)))


def _make_recommendation(
    *,
    code: str,
    priority: str,
    title: str,
    description: str,
    affected_user_ids: tuple[int, ...],
) -> ManagerActionRecommendation:
    return ManagerActionRecommendation(
        code=code,
        priority=priority,
        title=title,
        description=description,
        affected_employees_count=len(affected_user_ids),
        affected_user_ids=affected_user_ids,
        target_url=_recommendation_target_url(code),
    )


def _topic_tag_for_recommendation_code(
    code: str,
    analytics: ManagerTeamAnalytics,
) -> Optional[str]:
    if not code.startswith("quiz_topic:"):
        return None
    topic_slug = code[len("quiz_topic:") :]
    for index, topic in enumerate(analytics.development_topics):
        if (
            _safe_recommendation_code_fragment(
                topic.tag,
                fallback=f"topic-{index + 1}",
            )
            == topic_slug
        ):
            return topic.tag
    return None


def _practical_signal_text_for_recommendation_code(
    code: str,
    analytics: ManagerTeamAnalytics,
) -> Optional[str]:
    if not code.startswith("practical_signal:"):
        return None
    signal_slug = code[len("practical_signal:") :]
    for index, signal in enumerate(analytics.practical_development_areas):
        if (
            _safe_recommendation_code_fragment(
                signal.text,
                fallback=f"signal-{index + 1}",
            )
            == signal_slug
        ):
            return signal.text
    return None


def _member_topic_answers_count(
    row: ManagerTeamMemberAnalytics,
    topic_tag: str,
) -> int:
    for topic in row.topics_analytics.topics:
        if topic.tag == topic_tag:
            return topic.answers_count
    return 0


def _member_practical_signal_evidence_count(
    row: ManagerTeamMemberAnalytics,
    signal_text: str,
) -> int:
    signal_key = signal_text.casefold()
    for signal in row.practical_signal_evidence.development_areas:
        if signal.text.casefold() == signal_key:
            return signal.evidence_count
    return 0


def _member_recommendation_development_actions(
    recommendation: ManagerActionRecommendation,
    row: ManagerTeamMemberAnalytics,
) -> tuple[ManagerRecommendationDevelopmentAction, ...]:
    code = recommendation.code

    if code == "quiz_attention":
        actions: list[ManagerRecommendationDevelopmentAction] = []
        for course in row.quiz_analytics.courses:
            if course.latest_passed is False:
                actions.append(
                    ManagerRecommendationDevelopmentAction(
                        kind="course",
                        title=course.title,
                        description=(
                            f"Последний результат теста — {course.latest_score_percent}%. "
                            "Тест не пройден, рекомендуется повторить обучение."
                        ),
                        url=f"/courses/{course.slug}",
                    )
                )
        return tuple(actions)

    if code == "practical_attention":
        actions = []
        for attempt in row.practical_task_analytics.recent_attempts:
            if attempt.passed is False:
                score_text = ""
                if attempt.score_percent is not None:
                    score_text = f"Результат — {attempt.score_percent}%. "
                actions.append(
                    ManagerRecommendationDevelopmentAction(
                        kind="practical_task",
                        title=attempt.task_title,
                        description=(
                            f"{attempt.course_title}, {attempt.lesson_title}. "
                            f"{score_text}"
                            "Задание не принято, рекомендуется повторить практику."
                        ),
                        url=(
                            f"/courses/{attempt.course_slug}"
                            f"/lessons/{attempt.lesson_slug}"
                        ),
                    )
                )
        return tuple(actions)

    return ()


def _member_recommendation_reason(
    recommendation: ManagerActionRecommendation,
    row: ManagerTeamMemberAnalytics,
    analytics: ManagerTeamAnalytics,
) -> str:
    code = recommendation.code
    if code == "quiz_attention":
        failed_count = row.quiz_analytics.latest_failed_courses_count
        if failed_count > 0:
            return f"Последних непройденных курсов: {failed_count}."
        return (
            "Есть последняя непройденная попытка по одному или нескольким курсам."
        )

    if code == "practical_attention":
        failed_count = row.practical_task_analytics.failed_attempts_count
        return f"Есть непринятые практические задания: {failed_count}."

    if code == "practical_pending":
        pending_count = row.practical_task_analytics.pending_attempts_count
        return f"Практических заданий ожидает проверки: {pending_count}."

    if code == "quiz_no_data":
        return "Сотрудник ещё не проходил тестирование."

    if code == "learning_not_started":
        return "Сотрудник ещё не начал обучение."

    topic_tag = _topic_tag_for_recommendation_code(code, analytics)
    if topic_tag is not None:
        answers_count = _member_topic_answers_count(row, topic_tag)
        if answers_count > 0:
            return (
                f"У сотрудника есть ответы по теме «{topic_tag}». "
                f"Ответов по теме: {answers_count}."
            )
        return f"У сотрудника есть ответы по теме «{topic_tag}»."

    signal_text = _practical_signal_text_for_recommendation_code(code, analytics)
    if signal_text is not None:
        evidence_count = _member_practical_signal_evidence_count(row, signal_text)
        if evidence_count > 0:
            return (
                "Сигнал встречался в проверенных практических заданиях сотрудника. "
                f"Наблюдений: {evidence_count}."
            )
        return "Сигнал встречался в проверенных практических заданиях сотрудника."

    return "Сотрудник попадает под это рекомендуемое действие."


def _build_team_recommendations(
    analytics: ManagerTeamAnalytics,
    members: tuple[ManagerTeamMemberAnalytics, ...],
) -> tuple[ManagerActionRecommendation, ...]:
    recommendations: list[ManagerActionRecommendation] = []
    seen_codes: set[str] = set()

    def add_recommendation(recommendation: ManagerActionRecommendation) -> None:
        if recommendation.code in seen_codes:
            return
        if recommendation.affected_employees_count <= 0:
            return
        seen_codes.add(recommendation.code)
        recommendations.append(recommendation)

    quiz_attention_ids = _sorted_user_ids(
        row.member.user_id
        for row in members
        if row.quiz_analytics.latest_failed_courses_count > 0
    )
    if quiz_attention_ids:
        add_recommendation(
            _make_recommendation(
                code="quiz_attention",
                priority="high",
                title="Повторить обучение по непройденным тестам",
                description=(
                    "У части сотрудников последние попытки по курсам не пройдены. "
                    "Проверьте результаты и назначьте повторное обучение."
                ),
                affected_user_ids=quiz_attention_ids,
            )
        )

    practical_attention_ids = _sorted_user_ids(
        row.member.user_id
        for row in members
        if row.practical_task_analytics.failed_attempts_count > 0
    )
    if practical_attention_ids:
        add_recommendation(
            _make_recommendation(
                code="practical_attention",
                priority="high",
                title="Разобрать непринятые практические задания",
                description=(
                    "У части сотрудников есть непринятые практические задания. "
                    "Рекомендуется разобрать ошибки и повторить практику."
                ),
                affected_user_ids=practical_attention_ids,
            )
        )

    practical_pending_ids = _sorted_user_ids(
        row.member.user_id
        for row in members
        if row.practical_task_analytics.pending_attempts_count > 0
    )
    if practical_pending_ids:
        add_recommendation(
            _make_recommendation(
                code="practical_pending",
                priority="medium",
                title="Проверить ожидающие практические задания",
                description=(
                    "Есть практические задания, которые ожидают проверки "
                    "или завершения review-процесса."
                ),
                affected_user_ids=practical_pending_ids,
            )
        )

    quiz_no_data_ids = _sorted_user_ids(
        row.member.user_id
        for row in members
        if row.quiz_analytics.total_attempts_count == 0
    )
    if quiz_no_data_ids:
        add_recommendation(
            _make_recommendation(
                code="quiz_no_data",
                priority="medium",
                title="Получить данные по знаниям сотрудников",
                description=(
                    "Часть сотрудников ещё не проходила тестирование. "
                    "Без результатов сложно определить уровень знаний и зоны развития."
                ),
                affected_user_ids=quiz_no_data_ids,
            )
        )

    for index, topic in enumerate(analytics.development_topics):
        topic_slug = _safe_recommendation_code_fragment(
            topic.tag,
            fallback=f"topic-{index + 1}",
        )
        topic_code = f"quiz_topic:{topic_slug}"
        topic_user_ids = _sorted_user_ids(
            row.member.user_id
            for row in members
            if _member_topic_answers_count(row, topic.tag) > 0
        )
        if topic_user_ids:
            add_recommendation(
                _make_recommendation(
                    code=topic_code,
                    priority="high" if topic.accuracy_percent < 50.0 else "medium",
                    title=f"Повторить тему: {topic.tag}",
                    description=(
                        f"Точность команды по теме — {topic.accuracy_percent}% "
                        f"на основе {topic.answers_count} ответов "
                        f"от {topic.employees_count} сотрудников."
                    ),
                    affected_user_ids=topic_user_ids,
                )
            )

    for index, signal in enumerate(analytics.practical_development_areas):
        signal_slug = _safe_recommendation_code_fragment(
            signal.text,
            fallback=f"signal-{index + 1}",
        )
        signal_code = f"practical_signal:{signal_slug}"
        signal_key = signal.text.casefold()
        signal_user_ids = _sorted_user_ids(
            row.member.user_id
            for row in members
            if any(
                item.text.casefold() == signal_key and item.evidence_count > 0
                for item in row.practical_signal_evidence.development_areas
            )
        )
        if signal_user_ids:
            add_recommendation(
                _make_recommendation(
                    code=signal_code,
                    priority="medium",
                    title=f"Усилить практический навык: {signal.text}",
                    description=(
                        f"Сигнал повторяется у {signal.employees_count} сотрудников "
                        f"и встречается в {signal.evidence_count} проверенных заданиях."
                    ),
                    affected_user_ids=signal_user_ids,
                )
            )

    learning_not_started_ids = _sorted_user_ids(
        row.member.user_id
        for row in members
        if row.member.started_courses_count == 0
    )
    if learning_not_started_ids:
        add_recommendation(
            _make_recommendation(
                code="learning_not_started",
                priority="low",
                title="Подключить сотрудников, которые ещё не начали обучение",
                description="Часть сотрудников пока не начала ни одного курса.",
                affected_user_ids=learning_not_started_ids,
            )
        )

    return tuple(
        sorted(
            recommendations,
            key=lambda recommendation: (
                _recommendation_priority_rank(recommendation.priority),
                -recommendation.affected_employees_count,
                recommendation.code.casefold(),
                recommendation.code,
            ),
        )
    )


def _qualifying_team_practical_signals(
    aggregated: dict[str, dict[str, object]],
) -> tuple[ManagerTeamPracticalSignal, ...]:
    qualifying = [
        ManagerTeamPracticalSignal(
            text=str(info["display"]),
            evidence_count=int(info["evidence_count"]),
            employees_count=len(info["employee_ids"]),
        )
        for info in aggregated.values()
        if len(info["employee_ids"]) >= MIN_TEAM_PRACTICAL_SIGNAL_EMPLOYEES
    ]

    return tuple(
        sorted(
            qualifying,
            key=lambda signal: (
                -signal.employees_count,
                -signal.evidence_count,
                signal.text.casefold(),
                signal.text,
            ),
        )
    )
