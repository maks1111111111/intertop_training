"""View models for actionable practical development signal sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.content.runtime import ContentRuntime
from app.web.manager_employee_analytics_service import (
    EmployeeDevelopmentProfile,
    EmployeePracticalSignalSourceEvidence,
)


@dataclass(frozen=True)
class EmployeePracticalSignalSourceAction:
    course_slug: str
    course_title: str
    lesson_slug: str
    lesson_title: str
    evidence_count: int
    lesson_url: Optional[str]
    can_assign: bool


@dataclass(frozen=True)
class EmployeePracticalSignalActionableEvidence:
    text: str
    evidence_count: int
    sources: tuple[EmployeePracticalSignalSourceAction, ...]


def _runtime_lesson_exists(runtime_course, lesson_slug: str) -> bool:
    return any(lesson.path.name == lesson_slug for lesson in runtime_course.lessons)


def _map_source_action(
    source: EmployeePracticalSignalSourceEvidence,
    assignable_slugs: frozenset[str],
    runtime: ContentRuntime,
) -> EmployeePracticalSignalSourceAction:
    runtime_course = runtime.get_course(source.course_slug)
    lesson_url = None
    if runtime_course is not None and _runtime_lesson_exists(
        runtime_course,
        source.lesson_slug,
    ):
        lesson_url = f"/courses/{source.course_slug}/lessons/{source.lesson_slug}"
    return EmployeePracticalSignalSourceAction(
        course_slug=source.course_slug,
        course_title=source.course_title,
        lesson_slug=source.lesson_slug,
        lesson_title=source.lesson_title,
        evidence_count=source.evidence_count,
        lesson_url=lesson_url,
        can_assign=source.course_slug in assignable_slugs,
    )


def build_practical_development_actionable_evidence(
    development_profile: EmployeeDevelopmentProfile,
    assignable_courses: tuple,
    runtime: ContentRuntime,
) -> tuple[EmployeePracticalSignalActionableEvidence, ...]:
    """Map practical development signal evidence to manager-facing actions."""
    assignable_slugs = frozenset(course.slug for course in assignable_courses)
    actionable_items: list[EmployeePracticalSignalActionableEvidence] = []

    for evidence in development_profile.practical_development_evidence:
        source_actions = tuple(
            _map_source_action(source, assignable_slugs, runtime)
            for source in evidence.sources
        )
        actionable_items.append(
            EmployeePracticalSignalActionableEvidence(
                text=evidence.text,
                evidence_count=evidence.evidence_count,
                sources=source_actions,
            )
        )

    return tuple(actionable_items)
