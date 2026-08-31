"""Tests for manager course assignment Web service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from app.web.manager_course_assignment_service import (
    ManagerCourseAssignmentService,
)
from app.web.manager_team_service import ManagerTeamMember


def _course_with_lessons(
    slug: str,
    title: str,
    *,
    lesson_count: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        title=title,
        lessons=[SimpleNamespace()] * lesson_count,
    )


class FakeTeamService:
    """Small fake for tenant-scoped member lookup."""

    def __init__(
        self,
        member: Optional[ManagerTeamMember] = None,
    ) -> None:
        self.member = member
        self.calls: list[tuple[str, int]] = []

    def get_member(
        self,
        company_id: str,
        user_id: int,
    ) -> Optional[ManagerTeamMember]:
        self.calls.append((company_id, user_id))
        return self.member


class FakeProgressRepository:
    """Tracks assignment calls and returns a configured result."""

    def __init__(
        self,
        assign_result: bool = True,
    ) -> None:
        self.assign_result = assign_result
        self.assign_calls: list[tuple[Path, int, str, int]] = []

    def assign_course_to_user(
        self,
        db_path: Path,
        user_id: int,
        course_slug: str,
        *,
        assigned_by_user_id: int,
    ) -> bool:
        self.assign_calls.append(
            (
                db_path,
                user_id,
                course_slug,
                assigned_by_user_id,
            )
        )
        return self.assign_result


class FakeContentRuntime:
    """Returns configured published courses by slug."""

    def __init__(
        self,
        courses: dict[str, SimpleNamespace],
    ) -> None:
        self.courses = courses
        self.calls: list[str] = []

    def get_course(self, slug: str) -> Optional[SimpleNamespace]:
        self.calls.append(slug)
        return self.courses.get(slug)


def _member(user_id: int = 42) -> ManagerTeamMember:
    return ManagerTeamMember(
        user_id=user_id,
        display_name="Alice Smith",
        username="alice",
        role="student",
        role_label="Сотрудник",
        started_courses_count=0,
        completed_courses_count=0,
        average_progress_percent=0,
    )


class ManagerCourseAssignmentServiceTests(unittest.TestCase):
    """Verify tenant-scoped manager course assignment behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _service(
        self,
        *,
        member: Optional[ManagerTeamMember] = _member(),
        assign_result: bool = True,
        courses: Optional[dict[str, SimpleNamespace]] = None,
    ) -> tuple[
        ManagerCourseAssignmentService,
        FakeTeamService,
        FakeProgressRepository,
        FakeContentRuntime,
    ]:
        if courses is None:
            courses = {
                "retail-basics": _course_with_lessons(
                    "retail-basics",
                    "Retail Basics",
                ),
            }

        team_service = FakeTeamService(member=member)
        progress_repository = FakeProgressRepository(assign_result=assign_result)
        runtime = FakeContentRuntime(courses=courses)
        service = ManagerCourseAssignmentService(
            team_service=team_service,
            progress_repository=progress_repository,
            runtime=runtime,
            db_path=self.db_path,
        )
        return service, team_service, progress_repository, runtime

    def test_successful_assignment(self) -> None:
        service, team_service, progress_repository, runtime = self._service()

        result = service.assign_course(
            "  intertop  ",
            42,
            "  retail-basics  ",
            assigned_by_user_id=10,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.code, "assigned")
        self.assertEqual(result.user_id, 42)
        self.assertEqual(result.course_slug, "retail-basics")
        self.assertEqual(
            team_service.calls,
            [("intertop", 42)],
        )
        self.assertEqual(runtime.calls, ["retail-basics"])
        self.assertEqual(
            progress_repository.assign_calls,
            [(self.db_path, 42, "retail-basics", 10)],
        )

    def test_member_not_found_does_not_call_repository_or_runtime(self) -> None:
        service, team_service, progress_repository, runtime = self._service(
            member=None,
        )

        result = service.assign_course("intertop", 42, "retail-basics", assigned_by_user_id=10)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "member_not_found")
        self.assertEqual(team_service.calls, [("intertop", 42)])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_course_not_found_does_not_call_repository(self) -> None:
        service, team_service, progress_repository, runtime = self._service(
            courses={},
        )

        result = service.assign_course("intertop", 42, "missing-course", assigned_by_user_id=10)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "course_not_found")
        self.assertEqual(team_service.calls, [("intertop", 42)])
        self.assertEqual(runtime.calls, ["missing-course"])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_empty_course_returns_course_not_assignable_without_repository(
        self,
    ) -> None:
        service, team_service, progress_repository, runtime = self._service(
            courses={
                "empty-course": _course_with_lessons(
                    "empty-course",
                    "Empty Course",
                    lesson_count=0,
                ),
            },
        )

        result = service.assign_course("intertop", 42, "empty-course", assigned_by_user_id=10)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "course_not_assignable")
        self.assertEqual(result.message, "Курс пока нельзя назначить: в нём нет уроков.")
        self.assertEqual(team_service.calls, [("intertop", 42)])
        self.assertEqual(runtime.calls, ["empty-course"])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_course_with_lessons_still_assigns_successfully(self) -> None:
        service, team_service, progress_repository, runtime = self._service(
            courses={
                "with-lessons": _course_with_lessons(
                    "with-lessons",
                    "Course With Lessons",
                ),
            },
        )

        result = service.assign_course("intertop", 42, "with-lessons", assigned_by_user_id=10)

        self.assertTrue(result.success)
        self.assertEqual(result.code, "assigned")
        self.assertEqual(
            progress_repository.assign_calls,
            [(self.db_path, 42, "with-lessons", 10)],
        )

    def test_repository_failure_returns_assignment_failed(self) -> None:
        service, team_service, progress_repository, runtime = self._service(
            assign_result=False,
        )

        result = service.assign_course("intertop", 42, "retail-basics", assigned_by_user_id=10)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "assignment_failed")
        self.assertEqual(
            progress_repository.assign_calls,
            [(self.db_path, 42, "retail-basics", 10)],
        )

    def test_assignment_author_is_forwarded_to_repository(self) -> None:
        service, _, progress_repository, _ = self._service()

        result = service.assign_course(
            "intertop",
            42,
            "retail-basics",
            assigned_by_user_id=777,
        )

        self.assertTrue(result.success)
        self.assertEqual(
            progress_repository.assign_calls,
            [(self.db_path, 42, "retail-basics", 777)],
        )

    def test_invalid_assignment_author_rejected_before_dependencies(self) -> None:
        service, team_service, progress_repository, runtime = self._service()

        for invalid in (0, -1, True, "1"):
            with self.subTest(assigned_by_user_id=invalid):
                with self.assertRaises(ValueError):
                    service.assign_course(
                        "intertop",
                        42,
                        "retail-basics",
                        assigned_by_user_id=invalid,  # type: ignore[arg-type]
                    )

        self.assertEqual(team_service.calls, [])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_invalid_company_id_rejected_before_dependencies(self) -> None:
        service, team_service, progress_repository, runtime = self._service()

        with self.assertRaises(ValueError):
            service.assign_course("   ", 42, "retail-basics", assigned_by_user_id=10)

        self.assertEqual(team_service.calls, [])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_invalid_user_id_values_rejected_before_dependencies(self) -> None:
        service, team_service, progress_repository, runtime = self._service()

        for invalid_user_id in (0, -1, True, "1"):
            with self.subTest(user_id=invalid_user_id):
                with self.assertRaises(ValueError):
                    service.assign_course("intertop", invalid_user_id, "retail-basics", assigned_by_user_id=10)

        self.assertEqual(team_service.calls, [])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_invalid_course_slug_rejected_before_dependencies(self) -> None:
        service, team_service, progress_repository, runtime = self._service()

        for invalid_course_slug in ("", "   ", 123):
            with self.subTest(course_slug=invalid_course_slug):
                with self.assertRaises(ValueError):
                    service.assign_course("intertop", 42, invalid_course_slug, assigned_by_user_id=10)

        self.assertEqual(team_service.calls, [])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_tenant_check_happens_before_course_lookup_and_assignment(self) -> None:
        service, team_service, progress_repository, runtime = self._service(
            member=None,
        )

        service.assign_course("intertop", 42, "retail-basics", assigned_by_user_id=10)

        self.assertEqual(team_service.calls, [("intertop", 42)])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(progress_repository.assign_calls, [])

    def test_uses_canonical_user_id_from_member_not_input_telegram(self) -> None:
        member = _member(user_id=7)
        service, team_service, progress_repository, runtime = self._service(
            member=member,
        )

        result = service.assign_course("intertop", 7, "retail-basics", assigned_by_user_id=10)

        self.assertTrue(result.success)
        self.assertEqual(result.user_id, 7)
        self.assertEqual(progress_repository.assign_calls[0][1], 7)


if __name__ == "__main__":
    unittest.main()
