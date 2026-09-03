"""HTTP tests for the tenant-scoped manager team page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.dashboard_service import CourseDashboardItem
from app.web.manager_course_assignment_history_service import (
    ManagerCourseAssignmentHistory,
    ManagerCourseAssignmentHistoryItem,
)
from app.web.manager_course_assignment_service import ManagerCourseAssignmentResult
from app.web.manager_employee_analytics_service import (
    EmployeeCourseQuizAnalytics,
    EmployeeDevelopmentProfile,
    EmployeePracticalSignal,
    EmployeePracticalSignalEvidence,
    EmployeePracticalSignalEvidenceSet,
    EmployeePracticalSignalSourceEvidence,
    EmployeePracticalTaskAttemptAnalytics,
    EmployeePracticalTaskAnalytics,
    EmployeeQuizAnalytics,
    EmployeeQuizTopicAnalytics,
    EmployeeQuizTopicCourseEvidence,
    EmployeeQuizTopicEvidence,
    EmployeeQuizTopicsAnalytics,
    EmployeeQuizTopicClassification,
)
from app.web.manager_team_analytics_service import (
    ManagerActionRecommendation,
    ManagerRecommendationAffectedMember,
    ManagerRecommendationDetail,
    ManagerRecommendationDevelopmentAction,
    ManagerTeamAnalytics,
    ManagerTeamMemberAnalytics,
    ManagerTeamOverview,
    ManagerTeamPracticalSignal,
    ManagerTeamTopicAnalytics,
)
from app.web.manager_team_service import ManagerTeamMember
from app.web.router import (
    get_content_runtime,
    get_current_web_identity,
    get_dashboard_service,
    get_manager_course_assignment_history_service,
    get_manager_course_assignment_service,
    get_manager_employee_analytics_service,
    get_manager_team_analytics_service,
    get_manager_team_service,
)
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app


class FakeManagerCourseAssignmentHistoryService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self._empty = False

    def get_for_member(
        self,
        company_id: str,
        user_id: int,
    ) -> ManagerCourseAssignmentHistory:
        self.calls.append((company_id, user_id))
        if self._empty:
            return ManagerCourseAssignmentHistory(
                assignments=(),
                total_count=0,
                assigned_count=0,
                in_progress_count=0,
                completed_count=0,
                no_deadline_count=0,
                on_track_count=0,
                due_soon_count=0,
                overdue_count=0,
                completed_on_time_count=0,
                completed_late_count=0,
            )
        return ManagerCourseAssignmentHistory(
            assignments=(
                ManagerCourseAssignmentHistoryItem(
                    course_slug="alpha",
                    course_title="Assigned Alpha",
                    status="assigned",
                    status_label="Назначен",
                    progress_percent=0,
                    assigned_at="2026-08-31 10:00:00",
                    assigned_by_display_name="Anna Manager",
                    due_at="2026-09-15 18:00:00",
                    started_at=None,
                    completed_at=None,
                    compliance_status="due_soon",
                    compliance_status_label="Срок скоро",
                ),
                ManagerCourseAssignmentHistoryItem(
                    course_slug="beta",
                    course_title="Assigned Beta",
                    status="in_progress",
                    status_label="В процессе",
                    progress_percent=60,
                    assigned_at="2026-08-31 11:00:00",
                    assigned_by_display_name="Anna Manager",
                    due_at=None,
                    started_at="2026-08-31 12:00:00",
                    completed_at=None,
                    compliance_status="no_deadline",
                    compliance_status_label="Без срока",
                ),
                ManagerCourseAssignmentHistoryItem(
                    course_slug="gamma",
                    course_title="Assigned Gamma",
                    status="completed",
                    status_label="Завершён",
                    progress_percent=100,
                    assigned_at="2026-08-31 13:00:00",
                    assigned_by_display_name="Anna Manager",
                    due_at="2026-08-31 14:00:00",
                    started_at="2026-08-31 14:00:00",
                    completed_at="2026-08-31 15:00:00",
                    compliance_status="completed_late",
                    compliance_status_label="Завершён с опозданием",
                ),
                ManagerCourseAssignmentHistoryItem(
                    course_slug="delta",
                    course_title="Assigned Delta",
                    status="in_progress",
                    status_label="В процессе",
                    progress_percent=20,
                    assigned_at="2026-08-31 16:00:00",
                    assigned_by_display_name="Anna Manager",
                    due_at="2026-08-01 12:00:00",
                    started_at="2026-08-31 16:30:00",
                    completed_at=None,
                    compliance_status="overdue",
                    compliance_status_label="Просрочен",
                ),
            ),
            total_count=4,
            assigned_count=1,
            in_progress_count=2,
            completed_count=1,
            no_deadline_count=1,
            on_track_count=0,
            due_soon_count=1,
            overdue_count=1,
            completed_on_time_count=0,
            completed_late_count=1,
        )


class FakeManagerTeamService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_team(self, company_id: str) -> tuple[ManagerTeamMember, ...]:
        self.calls.append(company_id)
        return (
            ManagerTeamMember(
                user_id=2,
                display_name="E2E Student",
                username="web-e2e-student",
                role="student",
                role_label="Сотрудник",
                started_courses_count=1,
                completed_courses_count=0,
                average_progress_percent=100,
            ),
        )

    def get_member(
        self,
        company_id: str,
        user_id: int,
    ) -> ManagerTeamMember | None:
        self.calls.append(f"{company_id}:{user_id}")
        if user_id != 2:
            return None
        return ManagerTeamMember(
            user_id=2,
            display_name="E2E Student",
            username="web-e2e-student",
            role="student",
            role_label="Сотрудник",
            started_courses_count=1,
            completed_courses_count=0,
            average_progress_percent=100,
        )



class FakeAnalyticsService:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.topic_classification_calls: list[int] = []
        self.development_profile_calls: list[int] = []
        self.practical_task_calls: list[int] = []
        self._empty_practical_task_analytics = False
        self._pending_practical_task = False
        self._unknown_practical_task_status = False
        self._empty_development_profile = False
        self._development_profile_override: Optional[EmployeeDevelopmentProfile] = None

    def get_quiz_analytics(self, user_id: int) -> EmployeeQuizAnalytics:
        self.calls.append(user_id)
        return EmployeeQuizAnalytics(
            total_attempts_count=3,
            tested_courses_count=2,
            passed_courses_count=1,
            latest_failed_courses_count=1,
            best_score_percent=90.0,
            average_score_percent=75.0,
            courses=(
                EmployeeCourseQuizAnalytics(
                    slug="alpha",
                    title="Alpha Quiz",
                    attempts_count=2,
                    best_score_percent=90.0,
                    average_score_percent=80.0,
                    latest_score_percent=90.0,
                    latest_passed=True,
                    ever_passed=True,
                ),
                EmployeeCourseQuizAnalytics(
                    slug="beta",
                    title="Beta Quiz",
                    attempts_count=1,
                    best_score_percent=70.0,
                    average_score_percent=70.0,
                    latest_score_percent=60.0,
                    latest_passed=False,
                    ever_passed=True,
                ),
            ),
        )

    def get_quiz_topic_classification(
        self,
        user_id: int,
    ) -> EmployeeQuizTopicClassification:
        self.topic_classification_calls.append(user_id)
        return EmployeeQuizTopicClassification(
            strengths=(
                EmployeeQuizTopicAnalytics(
                    tag="Работа с клиентом",
                    answers_count=5,
                    correct_answers_count=5,
                    accuracy_percent=100.0,
                ),
            ),
            development_areas=(
                EmployeeQuizTopicAnalytics(
                    tag="Возвраты",
                    answers_count=4,
                    correct_answers_count=2,
                    accuracy_percent=50.0,
                ),
            ),
            unclassified_topics_count=1,
        )

    def get_development_profile(
        self,
        user_id: int,
    ) -> EmployeeDevelopmentProfile:
        self.development_profile_calls.append(user_id)
        if self._development_profile_override is not None:
            return self._development_profile_override
        if self._empty_development_profile:
            return FakeAnalyticsService.empty_development_profile()
        return EmployeeDevelopmentProfile(
            quiz_strengths=(
                EmployeeQuizTopicAnalytics(
                    tag="Работа с клиентом",
                    answers_count=5,
                    correct_answers_count=5,
                    accuracy_percent=100.0,
                ),
            ),
            quiz_development_areas=(
                EmployeeQuizTopicAnalytics(
                    tag="Возвраты",
                    answers_count=4,
                    correct_answers_count=2,
                    accuracy_percent=50.0,
                ),
            ),
            practical_strengths=(
                EmployeePracticalSignal(
                    text="Чёткая структура ответа",
                    evidence_count=2,
                ),
            ),
            practical_development_areas=(
                EmployeePracticalSignal(
                    text="Добавить больше деталей",
                    evidence_count=3,
                ),
            ),
            reviewed_practical_attempts_count=3,
            has_sufficient_practical_evidence=True,
            quiz_strength_evidence=(
                EmployeeQuizTopicEvidence(
                    tag="Работа с клиентом",
                    courses=(
                        EmployeeQuizTopicCourseEvidence(
                            course_slug="alpha",
                            course_title="Alpha Quiz Course",
                            answers_count=3,
                            correct_answers_count=3,
                            accuracy_percent=100.0,
                        ),
                        EmployeeQuizTopicCourseEvidence(
                            course_slug="beta",
                            course_title="Beta Quiz Course",
                            answers_count=2,
                            correct_answers_count=2,
                            accuracy_percent=100.0,
                        ),
                    ),
                ),
            ),
            quiz_development_evidence=(
                EmployeeQuizTopicEvidence(
                    tag="Возвраты",
                    courses=(
                        EmployeeQuizTopicCourseEvidence(
                            course_slug="gamma",
                            course_title="Gamma Returns Course",
                            answers_count=4,
                            correct_answers_count=2,
                            accuracy_percent=50.0,
                        ),
                        EmployeeQuizTopicCourseEvidence(
                            course_slug="beta",
                            course_title="Beta Course",
                            answers_count=2,
                            correct_answers_count=1,
                            accuracy_percent=50.0,
                        ),
                    ),
                ),
            ),
            practical_strength_evidence=(
                EmployeePracticalSignalEvidence(
                    text="Чёткая структура ответа",
                    evidence_count=2,
                    sources=(
                        EmployeePracticalSignalSourceEvidence(
                            course_slug="alpha",
                            course_title="Alpha Course",
                            lesson_slug="lesson_01",
                            lesson_title="Lesson One",
                            evidence_count=2,
                        ),
                    ),
                ),
            ),
            practical_development_evidence=(
                EmployeePracticalSignalEvidence(
                    text="Добавить больше деталей",
                    evidence_count=3,
                    sources=(
                        EmployeePracticalSignalSourceEvidence(
                            course_slug="alpha",
                            course_title="Alpha Course",
                            lesson_slug="lesson_01",
                            lesson_title="Lesson One",
                            evidence_count=2,
                        ),
                        EmployeePracticalSignalSourceEvidence(
                            course_slug="beta",
                            course_title="Beta Course",
                            lesson_slug="lesson_01",
                            lesson_title="Lesson One",
                            evidence_count=1,
                        ),
                    ),
                ),
            ),
        )

    def get_practical_task_analytics(
        self,
        user_id: int,
    ) -> EmployeePracticalTaskAnalytics:
        self.practical_task_calls.append(user_id)
        if self._empty_practical_task_analytics:
            return FakeAnalyticsService.empty_practical_task_analytics()
        if self._pending_practical_task:
            return EmployeePracticalTaskAnalytics(
                total_attempts_count=1,
                reviewed_attempts_count=0,
                passed_attempts_count=0,
                failed_attempts_count=0,
                pending_attempts_count=1,
                scorable_attempts_count=0,
                average_score_percent=None,
                best_score_percent=None,
                recent_attempts=(
                    EmployeePracticalTaskAttemptAnalytics(
                        attempt_id=101,
                        course_slug="alpha",
                        course_title="Alpha Course",
                        lesson_slug="lesson_01",
                        lesson_title="Lesson One",
                        task_title="Pending practical task",
                        status="pending",
                        score=None,
                        max_score=None,
                        score_percent=None,
                        passed=None,
                        feedback_summary=None,
                        strengths=(),
                        improvements=(),
                        started_at="2026-08-20 12:00:00",
                        reviewed_at=None,
                    ),
                ),
            )
        if self._unknown_practical_task_status:
            return EmployeePracticalTaskAnalytics(
                total_attempts_count=1,
                reviewed_attempts_count=0,
                passed_attempts_count=0,
                failed_attempts_count=0,
                pending_attempts_count=0,
                scorable_attempts_count=0,
                average_score_percent=None,
                best_score_percent=None,
                recent_attempts=(
                    EmployeePracticalTaskAttemptAnalytics(
                        attempt_id=102,
                        course_slug="alpha",
                        course_title="Alpha Course",
                        lesson_slug="lesson_01",
                        lesson_title="Lesson One",
                        task_title="Legacy practical task",
                        status="legacy",
                        score=None,
                        max_score=None,
                        score_percent=None,
                        passed=None,
                        feedback_summary=None,
                        strengths=(),
                        improvements=(),
                        started_at="2026-08-20 12:00:00",
                        reviewed_at=None,
                    ),
                ),
            )
        return EmployeePracticalTaskAnalytics(
            total_attempts_count=2,
            reviewed_attempts_count=2,
            passed_attempts_count=1,
            failed_attempts_count=1,
            pending_attempts_count=0,
            scorable_attempts_count=2,
            average_score_percent=75.0,
            best_score_percent=90.0,
            recent_attempts=(
                EmployeePracticalTaskAttemptAnalytics(
                    attempt_id=1,
                    course_slug="alpha",
                    course_title="Alpha Course",
                    lesson_slug="lesson_01",
                    lesson_title="Lesson One",
                    task_title="Inspect the work area",
                    status="reviewed",
                    score=9,
                    max_score=10,
                    score_percent=90.0,
                    passed=True,
                    feedback_summary="Strong practical answer.",
                    strengths=("Identified hazards",),
                    improvements=("Add more detail",),
                    started_at="2026-08-20 12:00:00",
                    reviewed_at="2026-08-20 12:05:00",
                ),
                EmployeePracticalTaskAttemptAnalytics(
                    attempt_id=2,
                    course_slug="alpha",
                    course_title="Alpha Course",
                    lesson_slug="lesson_02",
                    lesson_title="Lesson Two",
                    task_title="Handle customer complaint",
                    status="reviewed",
                    score=6,
                    max_score=10,
                    score_percent=60.0,
                    passed=False,
                    feedback_summary="Needs clearer steps.",
                    strengths=(),
                    improvements=("Use the service script",),
                    started_at="2026-08-19 12:00:00",
                    reviewed_at="2026-08-19 12:05:00",
                ),
            ),
        )

    @staticmethod
    def empty_analytics() -> EmployeeQuizAnalytics:
        return EmployeeQuizAnalytics(
            total_attempts_count=0,
            tested_courses_count=0,
            passed_courses_count=0,
            latest_failed_courses_count=0,
            best_score_percent=None,
            average_score_percent=None,
            courses=(),
        )

    @staticmethod
    def empty_development_profile() -> EmployeeDevelopmentProfile:
        return EmployeeDevelopmentProfile(
            quiz_strengths=(),
            quiz_development_areas=(),
            practical_strengths=(),
            practical_development_areas=(),
            reviewed_practical_attempts_count=0,
            has_sufficient_practical_evidence=False,
        )

    @staticmethod
    def empty_topic_classification() -> EmployeeQuizTopicClassification:
        return EmployeeQuizTopicClassification(
            strengths=(),
            development_areas=(),
            unclassified_topics_count=0,
        )

    @staticmethod
    def empty_practical_task_analytics() -> EmployeePracticalTaskAnalytics:
        return EmployeePracticalTaskAnalytics(
            total_attempts_count=0,
            reviewed_attempts_count=0,
            passed_attempts_count=0,
            failed_attempts_count=0,
            pending_attempts_count=0,
            scorable_attempts_count=0,
            average_score_percent=None,
            best_score_percent=None,
            recent_attempts=(),
        )


class FakeTeamAnalyticsService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.detail_calls: list[tuple[str, str]] = []
        self._empty = False
        self._quiz_analytics_override: EmployeeQuizAnalytics | None = None
        self._practical_analytics_override: EmployeePracticalTaskAnalytics | None = None
        self._assignment_history_override: ManagerCourseAssignmentHistory | None = None
        self._members_override: tuple[ManagerTeamMemberAnalytics, ...] | None = None
        self._recommendations_override: (
            tuple[ManagerActionRecommendation, ...] | None
        ) = None

    @staticmethod
    def _default_member() -> ManagerTeamMember:
        return ManagerTeamMember(
            user_id=2,
            display_name="E2E Student",
            username="web-e2e-student",
            role="student",
            role_label="Сотрудник",
            started_courses_count=1,
            completed_courses_count=0,
            average_progress_percent=100,
        )

    @staticmethod
    def _default_member_quiz_analytics() -> EmployeeQuizAnalytics:
        return EmployeeQuizAnalytics(
            total_attempts_count=3,
            tested_courses_count=2,
            passed_courses_count=1,
            latest_failed_courses_count=1,
            best_score_percent=90.0,
            average_score_percent=75.0,
            courses=(
                EmployeeCourseQuizAnalytics(
                    slug="alpha",
                    title="Alpha Quiz",
                    attempts_count=2,
                    best_score_percent=90.0,
                    average_score_percent=80.0,
                    latest_score_percent=90.0,
                    latest_passed=True,
                    ever_passed=True,
                ),
                EmployeeCourseQuizAnalytics(
                    slug="beta",
                    title="Beta Quiz",
                    attempts_count=1,
                    best_score_percent=70.0,
                    average_score_percent=70.0,
                    latest_score_percent=60.0,
                    latest_passed=False,
                    ever_passed=True,
                ),
            ),
        )

    def _resolve_member_quiz_analytics(self) -> EmployeeQuizAnalytics:
        if self._quiz_analytics_override is not None:
            return self._quiz_analytics_override
        return self._default_member_quiz_analytics()

    def _resolve_member_practical_analytics(self) -> EmployeePracticalTaskAnalytics:
        if self._practical_analytics_override is not None:
            return self._practical_analytics_override
        return self._default_member_practical_analytics()

    @staticmethod
    def _default_member_assignment_history() -> ManagerCourseAssignmentHistory:
        return ManagerCourseAssignmentHistory(
            assignments=(),
            total_count=4,
            assigned_count=1,
            in_progress_count=2,
            completed_count=1,
            no_deadline_count=1,
            on_track_count=0,
            due_soon_count=1,
            overdue_count=1,
            completed_on_time_count=0,
            completed_late_count=1,
        )

    @staticmethod
    def _empty_member_assignment_history() -> ManagerCourseAssignmentHistory:
        return ManagerCourseAssignmentHistory(
            assignments=(),
            total_count=0,
            assigned_count=0,
            in_progress_count=0,
            completed_count=0,
            no_deadline_count=0,
            on_track_count=0,
            due_soon_count=0,
            overdue_count=0,
            completed_on_time_count=0,
            completed_late_count=0,
        )

    def _resolve_member_assignment_history(self) -> ManagerCourseAssignmentHistory:
        if self._assignment_history_override is not None:
            return self._assignment_history_override
        return self._default_member_assignment_history()

    def _populated_analytics(self) -> ManagerTeamAnalytics:
        return ManagerTeamAnalytics(
            members_count=3,
            started_members_count=2,
            completed_members_count=1,
            average_progress_percent=66.67,
            members_with_quiz_results_count=2,
            members_requiring_attention_count=1,
            members_without_quiz_data_count=1,
            average_quiz_score_percent=78.5,
            strengths_topics=(
                ManagerTeamTopicAnalytics(
                    tag="Работа с клиентом",
                    answers_count=10,
                    correct_answers_count=9,
                    accuracy_percent=90.0,
                    employees_count=2,
                ),
            ),
            development_topics=(
                ManagerTeamTopicAnalytics(
                    tag="Возвраты",
                    answers_count=8,
                    correct_answers_count=3,
                    accuracy_percent=37.5,
                    employees_count=2,
                ),
            ),
            members_with_practical_attempts_count=2,
            members_with_pending_practical_tasks_count=1,
            members_with_failed_practical_tasks_count=1,
            practical_attempts_count=5,
            practical_reviewed_attempts_count=4,
            practical_passed_attempts_count=2,
            practical_failed_attempts_count=2,
            practical_pending_attempts_count=1,
            average_practical_score_percent=72.5,
            practical_strengths=(
                ManagerTeamPracticalSignal(
                    text="Чёткая структура ответа",
                    evidence_count=4,
                    employees_count=2,
                ),
            ),
            practical_development_areas=(
                ManagerTeamPracticalSignal(
                    text="Добавить больше деталей",
                    evidence_count=5,
                    employees_count=2,
                ),
            ),
            reviewed_practical_attempts_count=4,
            assignment_total_count=4,
            assignment_due_soon_count=1,
            assignment_overdue_count=1,
            members_with_due_soon_assignments_count=1,
            members_with_overdue_assignments_count=1,
        )

    def _populated_recommendations(self) -> tuple[ManagerActionRecommendation, ...]:
        return (
            ManagerActionRecommendation(
                code="quiz_attention",
                priority="high",
                title="Повторить обучение по непройденным тестам",
                description=(
                    "У части сотрудников последние попытки по курсам не пройдены. "
                    "Проверьте результаты и назначьте повторное обучение."
                ),
                affected_employees_count=1,
                affected_user_ids=(2,),
                target_url="/manager/team/recommendation?code=quiz_attention",
            ),
            ManagerActionRecommendation(
                code="quiz_topic:vozvraty",
                priority="high",
                title="Повторить тему: Возвраты",
                description=(
                    "Точность команды по теме — 37.5% "
                    "на основе 8 ответов от 2 сотрудников."
                ),
                affected_employees_count=2,
                affected_user_ids=(2,),
                target_url="/manager/team/recommendation?code=quiz_topic%3Avozvraty",
            ),
            ManagerActionRecommendation(
                code="practical_pending",
                priority="medium",
                title="Проверить ожидающие практические задания",
                description=(
                    "Есть практические задания, которые ожидают проверки "
                    "или завершения review-процесса."
                ),
                affected_employees_count=1,
                affected_user_ids=(2,),
                target_url="/manager/team/recommendation?code=practical_pending",
            ),
            ManagerActionRecommendation(
                code="practical_attention",
                priority="high",
                title="Разобрать непринятые практические задания",
                description=(
                    "У части сотрудников есть непринятые практические задания. "
                    "Рекомендуется разобрать ошибки и повторить практику."
                ),
                affected_employees_count=1,
                affected_user_ids=(2,),
                target_url="/manager/team/recommendation?code=practical_attention",
            ),
            ManagerActionRecommendation(
                code="learning_not_started",
                priority="low",
                title="Подключить сотрудников, которые ещё не начали обучение",
                description="Часть сотрудников пока не начала ни одного курса.",
                affected_employees_count=1,
                affected_user_ids=(2,),
                target_url="/manager/team/recommendation?code=learning_not_started",
            ),
            ManagerActionRecommendation(
                code="practical_signal:dobavit-bolshe-detaley",
                priority="medium",
                title="Усилить практический навык: Добавить больше деталей",
                description=(
                    "Сигнал повторяется у 2 сотрудников "
                    "и встречается в 5 проверенных заданиях."
                ),
                affected_employees_count=2,
                affected_user_ids=(2,),
                target_url=(
                    "/manager/team/recommendation"
                    "?code=practical_signal%3Adobavit-bolshe-detaley"
                ),
            ),
        )

    @staticmethod
    def _default_member_practical_analytics() -> EmployeePracticalTaskAnalytics:
        return EmployeePracticalTaskAnalytics(
            total_attempts_count=2,
            reviewed_attempts_count=2,
            passed_attempts_count=1,
            failed_attempts_count=1,
            pending_attempts_count=0,
            scorable_attempts_count=2,
            average_score_percent=75.0,
            best_score_percent=90.0,
            recent_attempts=(),
        )

    def _resolve_recommendations(self) -> tuple[ManagerActionRecommendation, ...]:
        if self._recommendations_override is not None:
            if isinstance(self._recommendations_override, ManagerActionRecommendation):
                return (self._recommendations_override,)
            return self._recommendations_override
        return self._populated_recommendations()

    def get_team_overview(self, company_id: str) -> ManagerTeamOverview:
        self.calls.append(company_id)
        if self._empty:
            return ManagerTeamOverview(
                analytics=ManagerTeamAnalytics(
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
                    assignment_total_count=0,
                    assignment_due_soon_count=0,
                    assignment_overdue_count=0,
                    members_with_due_soon_assignments_count=0,
                    members_with_overdue_assignments_count=0,
                ),
                members=(),
                recommendations=(),
            )
        if self._members_override is not None:
            return ManagerTeamOverview(
                analytics=self._populated_analytics(),
                members=self._members_override,
                recommendations=self._resolve_recommendations(),
            )
        member = self._default_member()
        quiz_analytics = self._resolve_member_quiz_analytics()
        practical_task_analytics = self._resolve_member_practical_analytics()
        assignment_history = self._resolve_member_assignment_history()
        return ManagerTeamOverview(
            analytics=self._populated_analytics(),
            members=(
                ManagerTeamMemberAnalytics(
                    member=member,
                    quiz_analytics=quiz_analytics,
                    practical_task_analytics=practical_task_analytics,
                    topics_analytics=EmployeeQuizTopicsAnalytics(
                        total_tagged_answers_count=0,
                        topics=(),
                    ),
                    practical_signal_evidence=EmployeePracticalSignalEvidenceSet(
                        strengths=(),
                        development_areas=(),
                        reviewed_attempts_count=0,
                    ),
                    assignment_history=assignment_history,
                ),
            ),
            recommendations=self._resolve_recommendations(),
        )

    def get_team_analytics(self, company_id: str) -> ManagerTeamAnalytics:
        return self.get_team_overview(company_id).analytics

    def get_recommendation_detail(
        self,
        company_id: str,
        recommendation_code: str,
    ) -> Optional[ManagerRecommendationDetail]:
        self.detail_calls.append((company_id, recommendation_code))
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
        member = self._default_member()
        development_actions = ()
        if recommendation.code == "quiz_attention":
            development_actions = (
                ManagerRecommendationDevelopmentAction(
                    kind="course",
                    title="Alpha Course",
                    description=(
                        "Последний результат теста — 55.0%. "
                        "Тест не пройден, рекомендуется повторить обучение."
                    ),
                    url="/courses/alpha",
                ),
            )
        elif recommendation.code == "practical_attention":
            development_actions = (
                ManagerRecommendationDevelopmentAction(
                    kind="practical_task",
                    title="Handle complaint",
                    description=(
                        "Alpha Course, Lesson 1. Результат — 40.0%. "
                        "Задание не принято, рекомендуется повторить практику."
                    ),
                    url="/courses/alpha/lessons/lesson-01",
                ),
            )
        return ManagerRecommendationDetail(
            recommendation=recommendation,
            members=(
                ManagerRecommendationAffectedMember(
                    user_id=member.user_id,
                    display_name=member.display_name,
                    username=member.username,
                    reason="Последних непройденных курсов: 1.",
                    profile_url=(
                        f"/manager/team/{member.user_id}"
                        f"{_fake_recommendation_profile_anchor(recommendation.code)}"
                    ),
                    development_actions=development_actions,
                ),
            ),
        )


def _fake_recommendation_profile_anchor(recommendation_code: str) -> str:
    if recommendation_code in {"assignment_overdue", "assignment_due_soon"}:
        return "#assignments"
    if recommendation_code == "quiz_attention":
        return "#quiz-analytics"
    if recommendation_code in {"practical_attention", "practical_pending"}:
        return "#practical-tasks"
    if recommendation_code.startswith("quiz_topic:") or recommendation_code.startswith(
        "practical_signal:"
    ):
        return "#development-profile"
    return ""



class FakeContentRuntimeForAssignment:
    """Return published courses with configurable lesson counts."""

    def __init__(self, lesson_counts: dict[str, int]) -> None:
        self.lesson_counts = lesson_counts

    def get_course(self, slug: str) -> Optional[SimpleNamespace]:
        if slug not in self.lesson_counts:
            return None

        lesson_count = self.lesson_counts[slug]
        lessons = [
            SimpleNamespace(path=SimpleNamespace(name=f"lesson_{index + 1:02d}"))
            for index in range(lesson_count)
        ]
        return SimpleNamespace(
            slug=slug,
            lessons=lessons,
        )


class FakeDashboardService:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_courses_for_user(
        self,
        user_id: int,
    ) -> tuple[CourseDashboardItem, ...]:
        self.calls.append(user_id)
        return (
            CourseDashboardItem(
                slug="alpha",
                title="Alpha Course",
                description="",
                status="in_progress",
                progress_percent=75,
                best_quiz_score=90.0,
                last_quiz_score=85.0,
                last_lesson_title="Lesson 1",
                continue_url="/courses/alpha",
            ),
            CourseDashboardItem(
                slug="beta",
                title="Beta Course",
                description="",
                status="not_started",
                progress_percent=0,
                best_quiz_score=None,
                last_quiz_score=None,
                last_lesson_title="",
                continue_url="/courses/beta",
            ),
            CourseDashboardItem(
                slug="empty-course",
                title="Empty Course",
                description="",
                status="not_started",
                progress_percent=0,
                best_quiz_score=None,
                last_quiz_score=None,
                last_lesson_title="",
                continue_url="/courses/empty-course",
            ),
            CourseDashboardItem(
                slug="gamma",
                title="Gamma Course",
                description="",
                status="assigned",
                progress_percent=0,
                best_quiz_score=None,
                last_quiz_score=None,
                last_lesson_title="",
                continue_url="/courses/gamma",
            ),
            CourseDashboardItem(
                slug="delta",
                title="Delta Course",
                description="",
                status="completed",
                progress_percent=100,
                best_quiz_score=100.0,
                last_quiz_score=100.0,
                last_lesson_title="Lesson Final",
                continue_url="/courses/delta",
            ),
        )


class FakeManagerCourseAssignmentService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str, int, Optional[str]]] = []
        self._result_code = "assigned"

    def assign_course(
        self,
        company_id: str,
        user_id: int,
        course_slug: str,
        assigned_by_user_id: int,
        *,
        due_at: Optional[str] = None,
    ) -> ManagerCourseAssignmentResult:
        self.calls.append(
            (
                company_id,
                user_id,
                course_slug,
                assigned_by_user_id,
                due_at,
            )
        )
        if user_id != 2:
            return ManagerCourseAssignmentResult(
                success=False,
                code="member_not_found",
                message="Сотрудник не найден в компании.",
                user_id=user_id,
                course_slug=course_slug.strip(),
            )
        normalized_slug = course_slug.strip()
        if normalized_slug == "missing-course":
            return ManagerCourseAssignmentResult(
                success=False,
                code="course_not_found",
                message="Курс не найден или недоступен.",
                user_id=user_id,
                course_slug=normalized_slug,
            )
        if normalized_slug == "empty-course":
            return ManagerCourseAssignmentResult(
                success=False,
                code="course_not_assignable",
                message="Курс пока нельзя назначить: в нём нет уроков.",
                user_id=user_id,
                course_slug=normalized_slug,
            )
        if self._result_code == "assignment_failed":
            return ManagerCourseAssignmentResult(
                success=False,
                code="assignment_failed",
                message="Не удалось назначить курс.",
                user_id=user_id,
                course_slug=normalized_slug,
            )
        return ManagerCourseAssignmentResult(
            success=True,
            code="assigned",
            message="Курс назначен сотруднику.",
            user_id=user_id,
            course_slug=normalized_slug,
        )



def _page_filter_member_row(
    user_id: int,
    display_name: str,
    *,
    latest_failed: int = 0,
    failed_practical: int = 0,
    pending_practical: int = 0,
    overdue: int = 0,
    due_soon: int = 0,
) -> ManagerTeamMemberAnalytics:
    return ManagerTeamMemberAnalytics(
        member=ManagerTeamMember(
            user_id=user_id,
            display_name=display_name,
            username=f"user-{user_id}",
            role="student",
            role_label="Сотрудник",
            started_courses_count=1,
            completed_courses_count=0,
            average_progress_percent=50,
        ),
        quiz_analytics=EmployeeQuizAnalytics(
            total_attempts_count=1 if latest_failed else 0,
            tested_courses_count=1 if latest_failed else 0,
            passed_courses_count=0,
            latest_failed_courses_count=latest_failed,
            best_score_percent=70.0,
            average_score_percent=70.0,
            courses=(),
        ),
        practical_task_analytics=EmployeePracticalTaskAnalytics(
            total_attempts_count=failed_practical + pending_practical,
            reviewed_attempts_count=failed_practical,
            passed_attempts_count=0,
            failed_attempts_count=failed_practical,
            pending_attempts_count=pending_practical,
            scorable_attempts_count=failed_practical,
            average_score_percent=40.0 if failed_practical else None,
            best_score_percent=40.0 if failed_practical else None,
            recent_attempts=(),
        ),
        topics_analytics=EmployeeQuizTopicsAnalytics(
            total_tagged_answers_count=0,
            topics=(),
        ),
        practical_signal_evidence=EmployeePracticalSignalEvidenceSet(
            strengths=(),
            development_areas=(),
            reviewed_attempts_count=0,
        ),
        assignment_history=ManagerCourseAssignmentHistory(
            assignments=(),
            total_count=overdue + due_soon,
            assigned_count=0,
            in_progress_count=0,
            completed_count=0,
            no_deadline_count=0,
            on_track_count=0,
            due_soon_count=due_soon,
            overdue_count=overdue,
            completed_on_time_count=0,
            completed_late_count=0,
        ),
    )


def _identity(role: str) -> WebIdentity:
    return WebIdentity(
        user_id=10,
        telegram_id=None,
        company_id="intertop",
        company_name="Intertop Retail",
        role=role,
    )


class ManagerTeamPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name) / "courses"
        self.courses_dir.mkdir()
        (
            self.app,
            self.db_tmp,
            self.db_path,
            self.upload_tmp,
        ) = _create_test_app(
            self.courses_dir,
            management_identity=False,
        )
        self.client = TestClient(self.app)
        self.team_service = FakeManagerTeamService()
        self.dashboard_service = FakeDashboardService()
        self.analytics_service = FakeAnalyticsService()
        self.team_analytics_service = FakeTeamAnalyticsService()
        self.assignment_service = FakeManagerCourseAssignmentService()
        self.assignment_history_service = FakeManagerCourseAssignmentHistoryService()
        self.content_runtime = FakeContentRuntimeForAssignment(
            {
                "alpha": 1,
                "beta": 1,
                "gamma": 1,
                "delta": 1,
                "empty-course": 0,
            }
        )
        self.app.dependency_overrides[get_manager_team_service] = lambda: self.team_service
        self.app.dependency_overrides[get_dashboard_service] = lambda: self.dashboard_service
        self.app.dependency_overrides[get_manager_employee_analytics_service] = (
            lambda: self.analytics_service
        )
        self.app.dependency_overrides[get_manager_team_analytics_service] = (
            lambda: self.team_analytics_service
        )
        self.app.dependency_overrides[get_manager_course_assignment_service] = (
            lambda: self.assignment_service
        )
        self.app.dependency_overrides[get_manager_course_assignment_history_service] = (
            lambda: self.assignment_history_service
        )
        self.app.dependency_overrides[get_content_runtime] = lambda: self.content_runtime

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _set_identity(self, role: str) -> None:
        identity = _identity(role)

        def provide_identity(request: Request) -> WebIdentity:
            request.state.web_identity = identity
            return identity

        self.app.dependency_overrides[get_current_web_identity] = provide_identity

    def test_manager_can_open_team_page(self) -> None:
        self._set_identity("manager")
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Команда", response.text)
        self.assertIn("E2E Student", response.text)
        self.assertIn("100%", response.text)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.team_analytics_service.calls, ["intertop"])
        self.assertIn("Аналитика команды", response.text)
        self.assertIn("66.67%", response.text)
        self.assertIn("78.5%", response.text)
        self.assertIn("Требуют внимания", response.text)
        self.assertIn("Сильные стороны и зоны развития команды", response.text)
        self.assertIn("Сильные стороны по тестам", response.text)
        self.assertIn("Зоны развития по тестам", response.text)
        self.assertIn("Работа с клиентом", response.text)
        self.assertIn("90.0%", response.text)
        self.assertIn("Возвраты", response.text)
        self.assertIn("37.5%", response.text)
        self.assertIn("По практическим заданиям", response.text)
        self.assertIn("Повторяющиеся сильные стороны команды", response.text)
        self.assertIn("Повторяющиеся зоны развития команды", response.text)
        self.assertIn("Чёткая структура ответа", response.text)
        self.assertIn("Добавить больше деталей", response.text)
        self.assertIn("Наблюдений", response.text)
        self.assertIn("Сотрудников", response.text)
        self.assertIn("Протестировано курсов", response.text)
        self.assertIn("75.0%", response.text)
        self.assertIn("Требует внимания", response.text)
        self.assertIn("Практические задания", response.text)
        self.assertIn("Выполняли практические задания", response.text)
        self.assertIn("72.5%", response.text)
        self.assertIn("Есть результаты", response.text)
        self.assertIn("Рекомендуемые действия", response.text)
        self.assertIn("Повторить обучение по непройденным тестам", response.text)
        self.assertIn("Повторить тему: Возвраты", response.text)
        self.assertIn("Высокий приоритет", response.text)
        self.assertIn("Средний приоритет", response.text)
        self.assertIn("Низкий приоритет", response.text)
        self.assertIn("Сотрудников", response.text)
        self.assertIn("Посмотреть сотрудников", response.text)
        self.assertIn("/manager/team/recommendation?code=quiz_attention", response.text)
        self.assertIn("Сроки назначений", response.text)
        self.assertIn("Всего назначений", response.text)
        self.assertIn("Срок скоро", response.text)
        self.assertIn("Просрочено", response.text)
        self.assertIn("Сотрудников со сроком скоро", response.text)
        self.assertIn("Сотрудников с просрочкой", response.text)
        self.assertIn("dashboard-compliance-badge--overdue", response.text)
        self.assertIn("Просрочено: 1", response.text)

    def test_manager_team_page_renders_due_soon_member_status(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._assignment_history_override = (
            ManagerCourseAssignmentHistory(
                assignments=(),
                total_count=2,
                assigned_count=0,
                in_progress_count=2,
                completed_count=0,
                no_deadline_count=0,
                on_track_count=0,
                due_soon_count=2,
                overdue_count=0,
                completed_on_time_count=0,
                completed_late_count=0,
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard-compliance-badge--due_soon", response.text)
        self.assertIn("Срок скоро: 2", response.text)
        self.assertNotIn("Просрочено: ", response.text)

    def test_manager_team_page_renders_on_track_member_status(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._assignment_history_override = (
            ManagerCourseAssignmentHistory(
                assignments=(),
                total_count=1,
                assigned_count=0,
                in_progress_count=1,
                completed_count=0,
                no_deadline_count=0,
                on_track_count=1,
                due_soon_count=0,
                overdue_count=0,
                completed_on_time_count=0,
                completed_late_count=0,
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard-compliance-badge--on_track", response.text)
        self.assertIn("Под контролем", response.text)

    def test_manager_team_page_renders_no_assignments_member_status(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._assignment_history_override = (
            FakeTeamAnalyticsService._empty_member_assignment_history()
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard-compliance-badge--no_deadline", response.text)
        self.assertIn("Нет назначений", response.text)

    def test_overdue_takes_precedence_over_due_soon_on_member_card(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._assignment_history_override = (
            ManagerCourseAssignmentHistory(
                assignments=(),
                total_count=3,
                assigned_count=0,
                in_progress_count=3,
                completed_count=0,
                no_deadline_count=0,
                on_track_count=0,
                due_soon_count=1,
                overdue_count=2,
                completed_on_time_count=0,
                completed_late_count=0,
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Просрочено: 2", response.text)
        self.assertNotIn("Срок скоро: 1", response.text)

    def test_manager_team_page_renders_empty_recommendations_message(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._empty = True

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Рекомендуемые действия", response.text)
        self.assertIn(
            "Сейчас нет действий, требующих внимания по доступным данным.",
            response.text,
        )

    def test_manager_team_page_renders_empty_team_analytics(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._empty = True

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Аналитика команды", response.text)
        self.assertIn("—", response.text)
        self.assertIn("Сроки назначений", response.text)
        self.assertIn("Всего назначений", response.text)
        self.assertIn(
            "Пока недостаточно данных для определения сильных сторон команды по тестам",
            response.text,
        )
        self.assertIn(
            "Пока недостаточно данных для определения зон развития команды по тестам",
            response.text,
        )
        self.assertIn(
            "Пока недостаточно данных по практическим заданиям для командных выводов.",
            response.text,
        )
        self.assertIn("—", response.text)

    def test_manager_team_page_renders_zero_practical_attempts(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._practical_analytics_override = (
            FakeAnalyticsService.empty_practical_task_analytics()
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Нет практических заданий", response.text)

    def test_manager_team_page_renders_pending_practical_status(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._practical_analytics_override = (
            EmployeePracticalTaskAnalytics(
                total_attempts_count=1,
                reviewed_attempts_count=0,
                passed_attempts_count=0,
                failed_attempts_count=0,
                pending_attempts_count=1,
                scorable_attempts_count=0,
                average_score_percent=None,
                best_score_percent=None,
                recent_attempts=(),
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ожидает проверки (1)", response.text)

    def test_manager_team_page_renders_failed_practical_status(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._practical_analytics_override = (
            EmployeePracticalTaskAnalytics(
                total_attempts_count=2,
                reviewed_attempts_count=2,
                passed_attempts_count=0,
                failed_attempts_count=2,
                pending_attempts_count=0,
                scorable_attempts_count=2,
                average_score_percent=40.0,
                best_score_percent=40.0,
                recent_attempts=(),
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Требует внимания", response.text)
        self.assertIn("40.0%", response.text)

    def test_manager_team_page_renders_zero_quiz_attempts(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._quiz_analytics_override = (
            FakeAnalyticsService.empty_analytics()
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Нет данных по тестам", response.text)
        self.assertNotIn("Протестировано курсов", response.text)
        self.assertEqual(self.analytics_service.calls, [])

    def test_manager_team_page_renders_quiz_results_without_failures(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._quiz_analytics_override = EmployeeQuizAnalytics(
            total_attempts_count=2,
            tested_courses_count=1,
            passed_courses_count=1,
            latest_failed_courses_count=0,
            best_score_percent=90.0,
            average_score_percent=85.0,
            courses=(),
        )
        self.team_analytics_service._practical_analytics_override = (
            FakeAnalyticsService.empty_practical_task_analytics()
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Есть результаты", response.text)
        self.assertIn("85.0%", response.text)
        self.assertNotIn(
            'dashboard-status-badge--in_progress">Требует внимания</span>',
            response.text,
        )
        self.assertEqual(self.analytics_service.calls, [])

    def _set_filter_members(
        self,
        *members: ManagerTeamMemberAnalytics,
    ) -> None:
        self.team_analytics_service._members_override = members

    def test_manager_team_page_renders_all_members_with_default_filter(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Overdue Employee", overdue=1),
            _page_filter_member_row(2, "Due Soon Employee", due_soon=1),
            _page_filter_member_row(3, "Healthy Employee"),
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team" class="admin-subnav-link is-active">Все</a>', response.text)
        self.assertIn("Overdue Employee", response.text)
        self.assertIn("Due Soon Employee", response.text)
        self.assertIn("Healthy Employee", response.text)

    def test_manager_team_page_attention_filter(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Overdue Employee", overdue=1),
            _page_filter_member_row(2, "Due Soon Employee", due_soon=1),
            _page_filter_member_row(3, "Failed Quiz", latest_failed=1),
            _page_filter_member_row(4, "Healthy Employee"),
        )

        response = self.client.get("/manager/team?filter=attention")

        self.assertEqual(response.status_code, 200)
        self.assertIn('filter=attention" class="admin-subnav-link is-active">', response.text)
        self.assertIn("Overdue Employee", response.text)
        self.assertIn("Failed Quiz", response.text)
        self.assertNotIn("Due Soon Employee", response.text)
        self.assertNotIn("Healthy Employee", response.text)

    def test_manager_team_page_overdue_filter(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Overdue Employee", overdue=2),
            _page_filter_member_row(2, "Due Soon Employee", due_soon=1),
        )

        response = self.client.get("/manager/team?filter=overdue")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Overdue Employee", response.text)
        self.assertNotIn("Due Soon Employee", response.text)

    def test_manager_team_page_due_soon_filter(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Mixed Employee", due_soon=1, overdue=1),
            _page_filter_member_row(2, "Due Soon Employee", due_soon=2),
        )

        response = self.client.get("/manager/team?filter=due_soon")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Due Soon Employee", response.text)
        self.assertNotIn("Mixed Employee", response.text)

    def test_manager_team_page_unknown_filter_behaves_as_all(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Overdue Employee", overdue=1),
            _page_filter_member_row(2, "Healthy Employee"),
        )

        response = self.client.get("/manager/team?filter=unknown")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team" class="admin-subnav-link is-active">Все</a>', response.text)
        self.assertIn("Overdue Employee", response.text)
        self.assertIn("Healthy Employee", response.text)
        self.assertNotIn("<script>", response.text)

    def test_manager_team_page_global_analytics_unchanged_under_filter(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Overdue Employee", overdue=1),
            _page_filter_member_row(2, "Healthy Employee"),
        )

        response = self.client.get("/manager/team?filter=overdue")

        self.assertEqual(response.status_code, 200)
        self.assertIn("66.67%", response.text)
        self.assertIn("78.5%", response.text)
        self.assertIn("Рекомендуемые действия", response.text)
        self.assertIn("Повторить обучение по непройденным тестам", response.text)

    def test_manager_team_page_recommendations_visible_under_filter(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(1, "Overdue Employee", overdue=1),
        )

        response = self.client.get("/manager/team?filter=overdue")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Рекомендуемые действия", response.text)
        self.assertIn("Посмотреть сотрудников", response.text)

    def test_manager_team_page_filtered_empty_message(self) -> None:
        self._set_identity("manager")
        self._set_filter_members(
            _page_filter_member_row(2, "Healthy Employee"),
        )

        response = self.client.get("/manager/team?filter=overdue")

        self.assertEqual(response.status_code, 200)
        self.assertIn("По выбранному фильтру сотрудников нет.", response.text)
        self.assertNotIn("Healthy Employee", response.text)

    def test_manager_team_page_real_empty_team_message(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._empty = True

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("В компании пока нет сотрудников.", response.text)
        self.assertNotIn("По выбранному фильтру сотрудников нет.", response.text)
        self.assertNotIn('aria-label="Фильтр сотрудников"', response.text)

    def test_admin_can_open_team_page(self) -> None:
        self._set_identity("admin")
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 200)

    def test_student_cannot_open_team_page_does_not_call_analytics(self) -> None:
        self._set_identity("student")
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.team_analytics_service.calls, [])

    def test_anonymous_cannot_open_team_page_does_not_call_analytics(self) -> None:
        response = self.client.get("/manager/team")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.team_analytics_service.calls, [])


    def test_manager_can_open_team_member_page(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("E2E Student", response.text)
        self.assertIn("Alpha Course", response.text)
        self.assertIn("75%", response.text)
        self.assertIn("90.0%", response.text)
        self.assertIn("85.0%", response.text)
        self.assertEqual(self.team_service.calls, ["intertop:2"])
        self.assertEqual(self.dashboard_service.calls, [2])
        self.assertEqual(self.analytics_service.calls, [2])
        self.assertIn("Результаты тестов", response.text)
        self.assertIn("Alpha Quiz", response.text)
        self.assertIn("Beta Quiz", response.text)
        self.assertIn("Пройден", response.text)
        self.assertIn("Не пройден", response.text)
        self.assertIn("Ранее был успешно сдан", response.text)
        self.assertIn("Сильные стороны и зоны развития", response.text)
        self.assertIn("Сильные стороны", response.text)
        self.assertIn("Зоны развития", response.text)
        self.assertIn("Работа с клиентом", response.text)
        self.assertIn("Возвраты", response.text)
        self.assertIn("100.0%", response.text)
        self.assertIn("50.0%", response.text)
        self.assertIn("Источники данных", response.text)
        self.assertIn("Alpha Quiz Course", response.text)
        self.assertIn("Beta Quiz Course", response.text)
        self.assertIn("Gamma Returns Course", response.text)
        self.assertIn("3 ответов · 100.0%", response.text)
        self.assertIn("4 ответов · 50.0%", response.text)
        self.assertEqual(self.analytics_service.development_profile_calls, [2])
        self.assertEqual(self.analytics_service.practical_task_calls, [2])
        self.assertIn("Практические задания", response.text)
        self.assertIn("По практическим заданиям", response.text)
        self.assertIn("Повторяющиеся сильные стороны", response.text)
        self.assertIn("Повторяющиеся зоны развития", response.text)
        self.assertIn("Чёткая структура ответа", response.text)
        self.assertIn("Добавить больше деталей", response.text)
        self.assertIn("Наблюдений: 2", response.text)
        self.assertIn("Наблюдений: 3", response.text)
        self.assertIn("Inspect the work area", response.text)
        self.assertIn("Handle customer complaint", response.text)
        self.assertIn("Strong practical answer.", response.text)
        self.assertIn("Identified hazards", response.text)
        self.assertIn("Add more detail", response.text)
        self.assertIn("75.0%", response.text)
        self.assertIn("Принято", response.text)
        self.assertIn("Не принято", response.text)
        self.assertIn("Назначить курс", response.text)
        self.assertIn("Beta Course", response.text)
        self.assertIn("Назначен", response.text)
        self.assertNotIn('value="alpha"', response.text)
        self.assertNotIn('value="gamma"', response.text)
        self.assertNotIn('value="delta"', response.text)
        self.assertNotIn('value="empty-course"', response.text)
        self.assertIn('value="beta"', response.text)

    def test_development_source_course_renders_open_course_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/courses/gamma"', response.text)
        self.assertIn('href="/courses/beta"', response.text)
        self.assertIn("Открыть курс", response.text)

    def test_assignable_development_source_renders_prefill_assign_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'href="/manager/team/2?assign_course=beta#assign-course"',
            response.text,
        )
        self.assertNotIn(
            '<input type="hidden" name="course_slug" value="beta">',
            response.text,
        )

    def test_assign_course_query_prefills_assignment_dropdown(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2?assign_course=beta")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<option\n                    value="beta"\n                    selected',
            response.text,
        )
        self.assertIn('id="assign-course-due-at"', response.text)

    def test_invalid_assign_course_query_does_not_prefill_dropdown(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2?assign_course=gamma")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            '<option\n                    value="gamma"\n                    selected',
            response.text,
        )
        self.assertNotIn(
            '<option\n                    value="gamma"',
            response.text,
        )

    def test_stale_assign_course_query_does_not_prefill_dropdown(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2?assign_course=missing-runtime")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('selected', response.text.split('id="assign-course-slug"')[1].split("</select>")[0])

    def test_non_assignable_development_source_has_no_inline_assign(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/courses/gamma"', response.text)
        self.assertNotIn(
            '<input type="hidden" name="course_slug" value="gamma">',
            response.text,
        )

    def test_strength_evidence_does_not_render_course_actions(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('href="/courses/alpha"', response.text)

    def test_development_source_missing_runtime_has_no_open_or_assign(self) -> None:
        self._set_identity("manager")
        self.analytics_service._development_profile_override = EmployeeDevelopmentProfile(
            quiz_strengths=(),
            quiz_development_areas=(
                EmployeeQuizTopicAnalytics(
                    tag="Missing course",
                    answers_count=3,
                    correct_answers_count=1,
                    accuracy_percent=33.33,
                ),
            ),
            practical_strengths=(),
            practical_development_areas=(),
            reviewed_practical_attempts_count=0,
            has_sufficient_practical_evidence=False,
            quiz_development_evidence=(
                EmployeeQuizTopicEvidence(
                    tag="Missing course",
                    courses=(
                        EmployeeQuizTopicCourseEvidence(
                            course_slug="missing-runtime",
                            course_title="Missing Runtime Course",
                            answers_count=3,
                            correct_answers_count=1,
                            accuracy_percent=33.33,
                        ),
                    ),
                ),
            ),
        )

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('href="/courses/missing-runtime"', response.text)
        self.assertNotIn(
            '<input type="hidden" name="course_slug" value="missing-runtime">',
            response.text,
        )

    def test_practical_development_source_renders_course_and_lesson(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha Course / Lesson One", response.text)
        self.assertIn("Beta Course / Lesson One", response.text)
        self.assertIn("Наблюдений: 2", response.text)
        self.assertIn("Наблюдений: 1", response.text)

    def test_practical_development_source_renders_open_lesson_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/courses/alpha/lessons/lesson_01"', response.text)
        self.assertIn('href="/courses/beta/lessons/lesson_01"', response.text)
        self.assertIn("Открыть урок", response.text)

    def test_assignable_practical_source_renders_prefill_assign_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        practical_assign_links = [
            link
            for link in response.text.split('href="')
            if "assign_course=beta" in link and "#assign-course" in link
        ]
        self.assertTrue(practical_assign_links)
        self.assertIn(
            '/manager/team/2?assign_course=beta#assign-course"',
            response.text,
        )
        self.assertNotIn(
            '<input type="hidden" name="course_slug" value="beta">',
            response.text,
        )

    def test_non_assignable_practical_source_has_no_assign_action(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/courses/alpha/lessons/lesson_01"', response.text)
        self.assertNotIn(
            'href="/manager/team/2?assign_course=alpha#assign-course"',
            response.text,
        )

    def test_practical_strength_source_renders_without_actions(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        strength_section = response.text.split("Повторяющиеся сильные стороны", 1)[1]
        strength_section = strength_section.split("Повторяющиеся зоны развития", 1)[0]
        self.assertIn("Alpha Course / Lesson One", strength_section)
        self.assertIn("Источники данных", strength_section)
        self.assertNotIn("Открыть урок", strength_section)
        self.assertNotIn("assign_course=", strength_section)

    def test_practical_development_missing_runtime_shows_evidence_without_links(
        self,
    ) -> None:
        self._set_identity("manager")
        self.analytics_service._development_profile_override = EmployeeDevelopmentProfile(
            quiz_strengths=(),
            quiz_development_areas=(),
            practical_strengths=(),
            practical_development_areas=(
                EmployeePracticalSignal(
                    text="Stale practical signal",
                    evidence_count=2,
                ),
            ),
            reviewed_practical_attempts_count=2,
            has_sufficient_practical_evidence=True,
            practical_development_evidence=(
                EmployeePracticalSignalEvidence(
                    text="Stale practical signal",
                    evidence_count=2,
                    sources=(
                        EmployeePracticalSignalSourceEvidence(
                            course_slug="missing-practical",
                            course_title="Missing Practical Course",
                            lesson_slug="stale_lesson",
                            lesson_title="Stale Lesson",
                            evidence_count=2,
                        ),
                    ),
                ),
            ),
        )

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Missing Practical Course / Stale Lesson", response.text)
        self.assertNotIn('href="/courses/missing-practical', response.text)
        self.assertNotIn(
            'href="/manager/team/2?assign_course=missing-practical#assign-course"',
            response.text,
        )

    def test_practical_development_stale_lesson_keeps_assign_when_course_assignable(
        self,
    ) -> None:
        self._set_identity("manager")
        self.analytics_service._development_profile_override = EmployeeDevelopmentProfile(
            quiz_strengths=(),
            quiz_development_areas=(),
            practical_strengths=(),
            practical_development_areas=(
                EmployeePracticalSignal(
                    text="Stale lesson signal",
                    evidence_count=2,
                ),
            ),
            reviewed_practical_attempts_count=2,
            has_sufficient_practical_evidence=True,
            practical_development_evidence=(
                EmployeePracticalSignalEvidence(
                    text="Stale lesson signal",
                    evidence_count=2,
                    sources=(
                        EmployeePracticalSignalSourceEvidence(
                            course_slug="beta",
                            course_title="Beta Course",
                            lesson_slug="removed_lesson",
                            lesson_title="Removed Lesson",
                            evidence_count=2,
                        ),
                    ),
                ),
            ),
        )

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Beta Course / Removed Lesson", response.text)
        self.assertNotIn('href="/courses/beta/lessons/removed_lesson"', response.text)
        self.assertIn(
            'href="/manager/team/2?assign_course=beta#assign-course"',
            response.text,
        )

    def test_team_member_page_renders_assignment_history(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.assignment_history_service.calls, [("intertop", 2)])
        self.assertIn("Назначенные курсы", response.text)
        self.assertIn("Всего назначено", response.text)
        self.assertIn("Ожидают начала", response.text)
        self.assertIn("Assigned Alpha", response.text)
        self.assertIn("Assigned Beta", response.text)
        self.assertIn("Assigned Gamma", response.text)
        self.assertIn("Назначил", response.text)
        self.assertIn("Anna Manager", response.text)
        self.assertIn("2026-08-31 10:00:00", response.text)
        self.assertIn("2026-08-31 12:00:00", response.text)
        self.assertIn("2026-08-31 15:00:00", response.text)
        self.assertIn("60%", response.text)
        self.assertIn("100%", response.text)
        self.assertIn("Срок прохождения", response.text)
        self.assertIn("2026-09-15 18:00:00", response.text)

    def test_team_member_page_renders_assignment_compliance_summary(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("В сроке", response.text)
        self.assertIn("Срок скоро", response.text)
        self.assertIn("Просрочено", response.text)
        self.assertIn("Завершено в срок", response.text)
        self.assertIn("С опозданием", response.text)

    def test_team_member_page_renders_assignment_compliance_badges(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard-compliance-badge--due_soon", response.text)
        self.assertIn("dashboard-compliance-badge--no_deadline", response.text)
        self.assertIn("dashboard-compliance-badge--overdue", response.text)
        self.assertIn("dashboard-compliance-badge--completed_late", response.text)
        self.assertIn("Срок скоро", response.text)
        self.assertIn("Просрочен", response.text)
        self.assertIn("Завершён с опозданием", response.text)
        self.assertIn("Без срока", response.text)
        self.assertIn("Assigned Delta", response.text)

    def test_team_member_page_renders_lifecycle_and_compliance_statuses_together(
        self,
    ) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard-status-badge--in_progress", response.text)
        self.assertIn("dashboard-compliance-badge--overdue", response.text)
        self.assertIn("В процессе", response.text)

    def test_team_member_page_renders_assignment_without_due_at_safely(
        self,
    ) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Assigned Beta", response.text)
        self.assertNotIn("2026-09-15 18:00:00", response.text.split("Assigned Beta")[1].split("Assigned Gamma")[0])

    def test_team_member_page_renders_due_at_assignment_form_field(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="due_at"', response.text)
        self.assertIn('type="datetime-local"', response.text)
        self.assertIn("Срок прохождения", response.text)
        self.assertIn("Необязательно", response.text)

    def test_team_member_page_renders_empty_assignment_history(self) -> None:
        self._set_identity("manager")
        self.assignment_history_service._empty = True

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.assignment_history_service.calls, [("intertop", 2)])
        self.assertIn("Назначенные курсы", response.text)
        self.assertIn(
            "Менеджер пока не назначал этому сотруднику курсы.",
            response.text,
        )

    def test_team_member_page_excludes_empty_course_from_assignment_dropdown(
        self,
    ) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Empty Course", response.text)
        self.assertNotIn('value="empty-course"', response.text)
        self.assertIn('value="beta"', response.text)

    def test_team_member_page_renders_assignment_success_message(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2?assignment=assigned")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Курс назначен сотруднику.", response.text)

    def test_team_member_page_renders_assignment_failure_messages(self) -> None:
        self._set_identity("manager")

        course_not_found = self.client.get(
            "/manager/team/2?assignment=course_not_found",
        )
        assignment_failed = self.client.get(
            "/manager/team/2?assignment=assignment_failed",
        )

        self.assertIn("Курс не найден или недоступен.", course_not_found.text)
        self.assertIn("Не удалось назначить курс.", assignment_failed.text)

    def test_team_member_page_renders_course_not_assignable_message(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/2?assignment=course_not_assignable",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Курс пока нельзя назначить: в нём нет уроков.",
            response.text,
        )

    def test_team_member_page_ignores_unknown_assignment_query(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/2?assignment=<script>alert(1)</script>",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", response.text)

    def test_manager_can_assign_course(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "alpha"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/manager/team/2?assignment=assigned")
        self.assertEqual(
            self.assignment_service.calls,
            [("intertop", 2, "alpha", 10, None)],
        )

    def test_admin_can_assign_course(self) -> None:
        self._set_identity("admin")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "beta"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.assignment_service.calls, [("intertop", 2, "beta", 10, None)])

    def test_student_cannot_assign_course(self) -> None:
        self._set_identity("student")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "alpha"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.assignment_service.calls, [])

    def test_anonymous_cannot_assign_course(self) -> None:
        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "alpha"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.assignment_service.calls, [])

    def test_assign_course_uses_identity_company_id(self) -> None:
        self._set_identity("manager")

        self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "beta"},
            follow_redirects=False,
        )

        self.assertEqual(self.assignment_service.calls[0][0], "intertop")

    def test_assign_course_uses_identity_user_id_as_author(self) -> None:
        self._set_identity("manager")

        self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "alpha"},
            follow_redirects=False,
        )

        self.assertEqual(
            self.assignment_service.calls,
            [("intertop", 2, "alpha", 10, None)],
        )

    def test_assign_course_course_not_found_redirects(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "missing-course"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/manager/team/2?assignment=course_not_found",
        )

    def test_assign_course_assignment_failed_redirects(self) -> None:
        self._set_identity("manager")
        self.assignment_service._result_code = "assignment_failed"

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "beta"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/manager/team/2?assignment=assignment_failed",
        )

    def test_assign_course_not_assignable_redirects(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={"course_slug": "empty-course"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/manager/team/2?assignment=course_not_assignable",
        )

    def test_assign_course_member_not_found_returns_404(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/99/assign-course",
            data={"course_slug": "beta"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.assignment_service.calls, [("intertop", 99, "beta", 10, None)])

    def test_assign_course_with_valid_due_at_passes_canonical_value(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={
                "course_slug": "alpha",
                "due_at": "2026-09-15T18:00",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/manager/team/2?assignment=assigned")
        self.assertEqual(
            self.assignment_service.calls,
            [("intertop", 2, "alpha", 10, "2026-09-15 18:00:00")],
        )

    def test_assign_course_with_blank_due_at_passes_none(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={
                "course_slug": "alpha",
                "due_at": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self.assignment_service.calls,
            [("intertop", 2, "alpha", 10, None)],
        )

    def test_assign_course_with_malformed_due_at_redirects_with_error(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={
                "course_slug": "alpha",
                "due_at": "not-a-date",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/manager/team/2?assignment=invalid_due_at",
        )
        self.assertEqual(self.assignment_service.calls, [])

    def test_assign_course_with_impossible_date_redirects_with_error(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={
                "course_slug": "alpha",
                "due_at": "2026-02-31T18:00",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/manager/team/2?assignment=invalid_due_at",
        )
        self.assertEqual(self.assignment_service.calls, [])

    def test_assign_course_with_impossible_time_redirects_with_error(self) -> None:
        self._set_identity("manager")

        response = self.client.post(
            "/manager/team/2/assign-course",
            data={
                "course_slug": "alpha",
                "due_at": "2026-09-15T25:00",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/manager/team/2?assignment=invalid_due_at",
        )
        self.assertEqual(self.assignment_service.calls, [])

    def test_team_member_page_renders_invalid_due_at_message(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2?assignment=invalid_due_at")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Некорректный срок прохождения.", response.text)

    def test_team_member_page_renders_empty_practical_task_analytics(self) -> None:
        self._set_identity("manager")
        self.analytics_service._empty_practical_task_analytics = True

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Практические задания", response.text)
        self.assertIn("Сотрудник пока не выполнял практические задания", response.text)

    def test_team_member_page_does_not_render_learner_answer(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("learner_answer", response.text.lower())

    def test_team_member_page_renders_pending_practical_task_state(self) -> None:
        self._set_identity("manager")
        self.analytics_service._pending_practical_task = True

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Pending practical task", response.text)
        self.assertIn("Ожидает проверки", response.text)

    def test_team_member_page_renders_unknown_practical_task_status_safely(self) -> None:
        self._set_identity("manager")
        self.analytics_service._unknown_practical_task_status = True

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Legacy practical task", response.text)
        self.assertIn("Статус недоступен", response.text)

    def test_team_member_page_renders_zero_attempt_analytics(self) -> None:
        self._set_identity("manager")
        self.analytics_service.get_quiz_analytics = (
            lambda user_id: FakeAnalyticsService.empty_analytics()
        )

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Результаты тестов", response.text)
        self.assertIn("Сотрудник пока не проходил тесты", response.text)

    def test_team_member_page_renders_empty_development_profile(self) -> None:
        self._set_identity("manager")
        self.analytics_service._empty_development_profile = True

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Пока недостаточно данных для определения сильных сторон и зон развития",
            response.text,
        )
        self.assertIn(
            "Недостаточно проверенных практических заданий для устойчивых выводов.",
            response.text,
        )

    def test_team_member_page_returns_404_outside_tenant(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/99")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.team_service.calls, ["intertop:99"])
        self.assertEqual(self.dashboard_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.analytics_service.development_profile_calls, [])
        self.assertEqual(self.analytics_service.practical_task_calls, [])
        self.assertEqual(self.assignment_history_service.calls, [])



    def test_student_cannot_open_team_member_page(self) -> None:
        self._set_identity("student")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.dashboard_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.analytics_service.development_profile_calls, [])
        self.assertEqual(self.analytics_service.practical_task_calls, [])
        self.assertEqual(self.assignment_history_service.calls, [])

    def test_anonymous_cannot_open_team_member_page(self) -> None:
        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.dashboard_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.analytics_service.development_profile_calls, [])
        self.assertEqual(self.analytics_service.practical_task_calls, [])
        self.assertEqual(self.assignment_history_service.calls, [])

    def test_manager_can_open_recommendation_detail_page(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "quiz_attention"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Рекомендуемое действие", response.text)
        self.assertIn("Повторить обучение по непройденным тестам", response.text)
        self.assertIn("Высокий приоритет", response.text)
        self.assertIn("E2E Student", response.text)
        self.assertIn("Последних непройденных курсов: 1.", response.text)
        self.assertIn("Что можно сделать", response.text)
        self.assertIn("Alpha Course", response.text)
        self.assertIn("55.0%", response.text)
        self.assertIn("Тест не пройден", response.text)
        self.assertIn("Открыть курс", response.text)
        self.assertIn("/courses/alpha", response.text)
        self.assertIn("Открыть профиль", response.text)
        self.assertIn("/manager/team/2#quiz-analytics", response.text)
        self.assertEqual(self.team_analytics_service.detail_calls, [("intertop", "quiz_attention")])

    def test_recommendation_detail_renders_practical_task_development_action(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "practical_attention"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Что можно сделать", response.text)
        self.assertIn("Handle complaint", response.text)
        self.assertIn("40.0%", response.text)
        self.assertIn("Задание не принято", response.text)
        self.assertIn("Открыть урок", response.text)
        self.assertIn("/courses/alpha/lessons/lesson-01", response.text)

    def test_admin_can_open_recommendation_detail_page(self) -> None:
        self._set_identity("admin")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "quiz_attention"},
        )

        self.assertEqual(response.status_code, 200)

    def test_student_cannot_open_recommendation_detail_page(self) -> None:
        self._set_identity("student")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "quiz_attention"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_analytics_service.detail_calls, [])

    def test_anonymous_cannot_open_recommendation_detail_page(self) -> None:
        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "quiz_attention"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_analytics_service.detail_calls, [])

    def test_unknown_recommendation_returns_404(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "unknown-code"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.team_analytics_service.detail_calls, [("intertop", "unknown-code")])

    def test_recommendation_detail_does_not_render_learner_answer(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "quiz_attention"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("learner_answer", response.text.lower())

    def test_manager_team_member_page_renders_section_anchors(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="assignments"', response.text)
        self.assertIn('id="quiz-analytics"', response.text)
        self.assertIn('id="practical-tasks"', response.text)
        self.assertIn('id="development-profile"', response.text)
        self.assertIn("profile-section-anchor", response.text)

    def test_manager_team_overdue_badge_links_to_assignments_section(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team/2#assignments"', response.text)
        self.assertIn(
            "dashboard-status-link dashboard-compliance-badge dashboard-compliance-badge--overdue",
            response.text,
        )
        self.assertIn("Просрочено: 1", response.text)

    def test_manager_team_due_soon_badge_links_to_assignments_section(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._assignment_history_override = (
            ManagerCourseAssignmentHistory(
                assignments=(),
                total_count=2,
                assigned_count=0,
                in_progress_count=2,
                completed_count=0,
                no_deadline_count=0,
                on_track_count=0,
                due_soon_count=2,
                overdue_count=0,
                completed_on_time_count=0,
                completed_late_count=0,
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team/2#assignments"', response.text)
        self.assertIn(
            "dashboard-status-link dashboard-compliance-badge dashboard-compliance-badge--due_soon",
            response.text,
        )
        self.assertIn("Срок скоро: 2", response.text)

    def test_manager_team_failed_quiz_links_to_quiz_analytics(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team/2#quiz-analytics"', response.text)
        self.assertIn(
            "dashboard-status-link dashboard-status-badge dashboard-status-badge--in_progress",
            response.text,
        )

    def test_manager_team_pending_practical_links_to_practical_tasks(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._practical_analytics_override = (
            EmployeePracticalTaskAnalytics(
                total_attempts_count=1,
                reviewed_attempts_count=0,
                passed_attempts_count=0,
                failed_attempts_count=0,
                pending_attempts_count=1,
                scorable_attempts_count=0,
                average_score_percent=None,
                best_score_percent=None,
                recent_attempts=(),
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team/2#practical-tasks"', response.text)
        self.assertIn(
            "dashboard-status-link dashboard-status-badge dashboard-status-badge--in_progress",
            response.text,
        )
        self.assertIn("Ожидает проверки (1)", response.text)

    def test_manager_team_failed_practical_links_to_practical_tasks(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._practical_analytics_override = (
            EmployeePracticalTaskAnalytics(
                total_attempts_count=2,
                reviewed_attempts_count=2,
                passed_attempts_count=0,
                failed_attempts_count=2,
                pending_attempts_count=0,
                scorable_attempts_count=2,
                average_score_percent=40.0,
                best_score_percent=40.0,
                recent_attempts=(),
            )
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/manager/team/2#practical-tasks"', response.text)
        self.assertIn(
            "dashboard-status-link dashboard-status-badge dashboard-status-badge--in_progress",
            response.text,
        )

    def test_manager_team_neutral_statuses_are_not_action_links(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._quiz_analytics_override = EmployeeQuizAnalytics(
            total_attempts_count=2,
            tested_courses_count=1,
            passed_courses_count=1,
            latest_failed_courses_count=0,
            best_score_percent=90.0,
            average_score_percent=85.0,
            courses=(),
        )
        self.team_analytics_service._practical_analytics_override = (
            FakeAnalyticsService.empty_practical_task_analytics()
        )
        self.team_analytics_service._assignment_history_override = (
            FakeTeamAnalyticsService._empty_member_assignment_history()
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Есть результаты", response.text)
        self.assertIn("Нет назначений", response.text)
        self.assertNotIn('href="/manager/team/2#quiz-analytics"', response.text)
        self.assertNotIn('href="/manager/team/2#practical-tasks"', response.text)
        self.assertNotIn('href="/manager/team/2#assignments"', response.text)

    def test_recommendation_detail_practical_attention_links_to_practical_tasks(
        self,
    ) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "practical_attention"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("/manager/team/2#practical-tasks", response.text)

    def test_quiz_development_topic_renders_recommendation_drill_down_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Зоны развития по тестам", response.text)
        self.assertIn("Возвраты", response.text)
        returns_section = response.text.split("Возвраты", 1)[1].split("</li>", 1)[0]
        self.assertIn("Посмотреть сотрудников", returns_section)
        self.assertIn(
            "/manager/team/recommendation?code=quiz_topic%3Avozvraty",
            returns_section,
        )

    def test_practical_development_signal_renders_recommendation_drill_down_link(
        self,
    ) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Повторяющиеся зоны развития команды", response.text)
        self.assertIn("Добавить больше деталей", response.text)
        signal_section = response.text.split("Добавить больше деталей", 1)[1].split(
            "</li>", 1
        )[0]
        self.assertIn("Посмотреть сотрудников", signal_section)
        self.assertIn(
            "/manager/team/recommendation?code=practical_signal%3Adobavit-bolshe-detaley",
            signal_section,
        )

    def test_quiz_strength_topic_has_no_development_drill_down_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Сильные стороны по тестам", response.text)
        strength_section = response.text.split("Работа с клиентом", 1)[1].split(
            "</li>", 1
        )[0]
        self.assertNotIn("Посмотреть сотрудников", strength_section)

    def test_practical_strength_signal_has_no_development_drill_down_link(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        strength_section = response.text.split("Чёткая структура ответа", 1)[1].split(
            "</li>", 1
        )[0]
        self.assertNotIn("Посмотреть сотрудников", strength_section)

    def test_development_topic_without_matching_recommendation_has_no_invented_url(
        self,
    ) -> None:
        self._set_identity("manager")
        self.team_analytics_service._recommendations_override = (
            ManagerActionRecommendation(
                code="quiz_attention",
                priority="high",
                title="Повторить обучение по непройденным тестам",
                description="Test",
                affected_employees_count=1,
                affected_user_ids=(2,),
                target_url="/manager/team/recommendation?code=quiz_attention",
            ),
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        returns_section = response.text.split("Возвраты", 1)[1].split("</li>", 1)[0]
        self.assertNotIn("quiz_topic", returns_section)
        self.assertNotIn("Посмотреть сотрудников", returns_section)

    def test_quiz_topic_recommendation_detail_links_to_development_profile(self) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={"code": "quiz_topic:vozvraty"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("/manager/team/2#development-profile", response.text)

    def test_practical_signal_recommendation_detail_links_to_development_profile(
        self,
    ) -> None:
        self._set_identity("manager")

        response = self.client.get(
            "/manager/team/recommendation",
            params={
                "code": "practical_signal:dobavit-bolshe-detaley",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("/manager/team/2#development-profile", response.text)

    def test_manager_team_page_uses_single_team_overview_call(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.team_analytics_service.calls, ["intertop"])


if __name__ == "__main__":
    unittest.main()
