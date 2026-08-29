"""HTTP tests for the tenant-scoped manager team page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.web.dashboard_service import CourseDashboardItem
from app.web.manager_employee_analytics_service import (
    EmployeeCourseQuizAnalytics,
    EmployeePracticalTaskAttemptAnalytics,
    EmployeePracticalTaskAnalytics,
    EmployeeQuizAnalytics,
    EmployeeQuizTopicAnalytics,
    EmployeeQuizTopicClassification,
)
from app.web.manager_team_analytics_service import (
    ManagerTeamAnalytics,
    ManagerTeamMemberAnalytics,
    ManagerTeamOverview,
    ManagerTeamTopicAnalytics,
)
from app.web.manager_team_service import ManagerTeamMember
from app.web.router import (
    get_current_web_identity,
    get_dashboard_service,
    get_manager_employee_analytics_service,
    get_manager_team_analytics_service,
    get_manager_team_service,
)
from app.web.web_identity_service import WebIdentity
from tests.web.test_web_ui import _create_test_app


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
        self.practical_task_calls: list[int] = []
        self._empty_practical_task_analytics = False
        self._pending_practical_task = False
        self._unknown_practical_task_status = False

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
            average_score_percent=None,
            best_score_percent=None,
            recent_attempts=(),
        )


class FakeTeamAnalyticsService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._empty = False
        self._quiz_analytics_override: EmployeeQuizAnalytics | None = None

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
            development_topics=(
                ManagerTeamTopicAnalytics(
                    tag="Возвраты",
                    answers_count=8,
                    correct_answers_count=3,
                    accuracy_percent=37.5,
                    employees_count=2,
                ),
            ),
        )

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
                    development_topics=(),
                ),
                members=(),
            )
        member = self._default_member()
        quiz_analytics = self._resolve_member_quiz_analytics()
        return ManagerTeamOverview(
            analytics=self._populated_analytics(),
            members=(
                ManagerTeamMemberAnalytics(
                    member=member,
                    quiz_analytics=quiz_analytics,
                ),
            ),
        )

    def get_team_analytics(self, company_id: str) -> ManagerTeamAnalytics:
        return self.get_team_overview(company_id).analytics



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
        self.app.dependency_overrides[get_manager_team_service] = lambda: self.team_service
        self.app.dependency_overrides[get_dashboard_service] = lambda: self.dashboard_service
        self.app.dependency_overrides[get_manager_employee_analytics_service] = (
            lambda: self.analytics_service
        )
        self.app.dependency_overrides[get_manager_team_analytics_service] = (
            lambda: self.team_analytics_service
        )

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
        self.assertIn("Зоны развития команды", response.text)
        self.assertIn("Возвраты", response.text)
        self.assertIn("37.5%", response.text)
        self.assertIn("Протестировано курсов", response.text)
        self.assertIn("75.0%", response.text)
        self.assertIn("Требует внимания", response.text)

    def test_manager_team_page_renders_empty_team_analytics(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._empty = True

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Аналитика команды", response.text)
        self.assertIn("—", response.text)
        self.assertIn(
            "Пока недостаточно данных для определения зон развития команды",
            response.text,
        )

    def test_manager_team_page_renders_zero_quiz_attempts(self) -> None:
        self._set_identity("manager")
        self.team_analytics_service._quiz_analytics_override = (
            FakeAnalyticsService.empty_analytics()
        )

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Нет данных по тестам", response.text)
        self.assertNotIn(
            '<span class="dashboard-metric-label">Средний результат</span>',
            response.text,
        )
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

        response = self.client.get("/manager/team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Есть результаты", response.text)
        self.assertIn("85.0%", response.text)
        self.assertNotIn("Требует внимания", response.text)
        self.assertEqual(self.analytics_service.calls, [])

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
        self.assertIn("Недостаточно данных или нейтральный результат по темам: 1", response.text)
        self.assertEqual(self.analytics_service.topic_classification_calls, [2])
        self.assertEqual(self.analytics_service.practical_task_calls, [2])
        self.assertIn("Практические задания", response.text)
        self.assertIn("Inspect the work area", response.text)
        self.assertIn("Handle customer complaint", response.text)
        self.assertIn("Strong practical answer.", response.text)
        self.assertIn("Identified hazards", response.text)
        self.assertIn("Add more detail", response.text)
        self.assertIn("75.0%", response.text)
        self.assertIn("Принято", response.text)
        self.assertIn("Не принято", response.text)

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

    def test_team_member_page_renders_empty_topic_classification(self) -> None:
        self._set_identity("manager")
        self.analytics_service.get_quiz_topic_classification = (
            lambda user_id: FakeAnalyticsService.empty_topic_classification()
        )

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Пока недостаточно данных для определения сильных сторон и зон развития",
            response.text,
        )

    def test_team_member_page_returns_404_outside_tenant(self) -> None:
        self._set_identity("manager")

        response = self.client.get("/manager/team/99")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.team_service.calls, ["intertop:99"])
        self.assertEqual(self.dashboard_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.analytics_service.topic_classification_calls, [])
        self.assertEqual(self.analytics_service.practical_task_calls, [])



    def test_student_cannot_open_team_member_page(self) -> None:
        self._set_identity("student")

        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.dashboard_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.analytics_service.topic_classification_calls, [])
        self.assertEqual(self.analytics_service.practical_task_calls, [])

    def test_anonymous_cannot_open_team_member_page(self) -> None:
        response = self.client.get("/manager/team/2")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.team_service.calls, [])
        self.assertEqual(self.dashboard_service.calls, [])
        self.assertEqual(self.analytics_service.calls, [])
        self.assertEqual(self.analytics_service.topic_classification_calls, [])
        self.assertEqual(self.analytics_service.practical_task_calls, [])



if __name__ == "__main__":
    unittest.main()
