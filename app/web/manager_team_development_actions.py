"""View models linking team development analytics to recommendation drill-down."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.web.manager_team_analytics_service import (
    ManagerActionRecommendation,
    ManagerTeamAnalytics,
    ManagerTeamPracticalSignal,
    ManagerTeamTopicAnalytics,
    recommendation_code_for_development_topic,
    recommendation_code_for_practical_signal,
)


@dataclass(frozen=True)
class ManagerTeamDevelopmentAction:
    label: str
    target_url: str


@dataclass(frozen=True)
class ManagerTeamTopicDevelopmentAction:
    topic: ManagerTeamTopicAnalytics
    action: Optional[ManagerTeamDevelopmentAction]


@dataclass(frozen=True)
class ManagerTeamPracticalDevelopmentAction:
    signal: ManagerTeamPracticalSignal
    action: Optional[ManagerTeamDevelopmentAction]


def _lookup_recommendation_action(
    recommendations_by_code: dict[str, ManagerActionRecommendation],
    code: str,
) -> Optional[ManagerTeamDevelopmentAction]:
    recommendation = recommendations_by_code.get(code)
    if recommendation is None or not recommendation.target_url:
        return None
    return ManagerTeamDevelopmentAction(
        label="Посмотреть сотрудников",
        target_url=recommendation.target_url,
    )


def build_team_topic_development_actions(
    team_analytics: ManagerTeamAnalytics,
    recommendations: tuple[ManagerActionRecommendation, ...],
) -> tuple[ManagerTeamTopicDevelopmentAction, ...]:
    """Map quiz development topics to existing recommendation drill-down URLs."""
    recommendations_by_code = {
        recommendation.code: recommendation for recommendation in recommendations
    }
    return tuple(
        ManagerTeamTopicDevelopmentAction(
            topic=topic,
            action=_lookup_recommendation_action(
                recommendations_by_code,
                recommendation_code_for_development_topic(topic, index),
            ),
        )
        for index, topic in enumerate(team_analytics.development_topics)
    )


def build_team_practical_development_actions(
    team_analytics: ManagerTeamAnalytics,
    recommendations: tuple[ManagerActionRecommendation, ...],
) -> tuple[ManagerTeamPracticalDevelopmentAction, ...]:
    """Map practical development signals to existing recommendation drill-down URLs."""
    recommendations_by_code = {
        recommendation.code: recommendation for recommendation in recommendations
    }
    return tuple(
        ManagerTeamPracticalDevelopmentAction(
            signal=signal,
            action=_lookup_recommendation_action(
                recommendations_by_code,
                recommendation_code_for_practical_signal(signal, index),
            ),
        )
        for index, signal in enumerate(team_analytics.practical_development_areas)
    )
