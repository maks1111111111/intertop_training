"""View models for actionable quiz development area course sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.content.runtime import ContentRuntime
from app.web.manager_employee_analytics_service import (
    EmployeeDevelopmentProfile,
    EmployeeQuizTopicCourseEvidence,
)


@dataclass(frozen=True)
class EmployeeQuizTopicCourseAction:
    course_slug: str
    course_title: str
    answers_count: int
    correct_answers_count: int
    accuracy_percent: float
    course_url: Optional[str]
    can_assign: bool


@dataclass(frozen=True)
class EmployeeQuizTopicActionableEvidence:
    tag: str
    courses: tuple[EmployeeQuizTopicCourseAction, ...]


def _map_course_action(
    course: EmployeeQuizTopicCourseEvidence,
    assignable_slugs: frozenset[str],
    runtime: ContentRuntime,
) -> EmployeeQuizTopicCourseAction:
    runtime_course = runtime.get_course(course.course_slug)
    course_url = (
        f"/courses/{course.course_slug}" if runtime_course is not None else None
    )
    return EmployeeQuizTopicCourseAction(
        course_slug=course.course_slug,
        course_title=course.course_title,
        answers_count=course.answers_count,
        correct_answers_count=course.correct_answers_count,
        accuracy_percent=course.accuracy_percent,
        course_url=course_url,
        can_assign=course.course_slug in assignable_slugs,
    )


def build_quiz_development_actionable_evidence(
    development_profile: EmployeeDevelopmentProfile,
    assignable_courses: tuple,
    runtime: ContentRuntime,
) -> tuple[EmployeeQuizTopicActionableEvidence, ...]:
    """Map development-area course evidence to manager-facing actions."""
    assignable_slugs = frozenset(course.slug for course in assignable_courses)
    actionable_items: list[EmployeeQuizTopicActionableEvidence] = []

    for evidence in development_profile.quiz_development_evidence:
        course_actions = tuple(
            _map_course_action(course, assignable_slugs, runtime)
            for course in evidence.courses
        )
        actionable_items.append(
            EmployeeQuizTopicActionableEvidence(
                tag=evidence.tag,
                courses=course_actions,
            )
        )

    return tuple(actionable_items)
