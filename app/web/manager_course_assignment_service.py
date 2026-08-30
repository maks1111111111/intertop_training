"""Tenant-scoped manager course assignment for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.content.runtime import ContentRuntime
from app.repositories.progress_repository import ProgressRepository
from app.web.manager_team_service import ManagerTeamService


@dataclass(frozen=True)
class ManagerCourseAssignmentResult:
    """Outcome of one manager course assignment attempt."""

    success: bool
    code: str
    message: str
    user_id: int
    course_slug: str


class ManagerCourseAssignmentService:
    """Assign published courses to tenant-scoped team members."""

    def __init__(
        self,
        team_service: ManagerTeamService,
        progress_repository: ProgressRepository,
        runtime: ContentRuntime,
        db_path: Path,
    ) -> None:
        self._team_service = team_service
        self._progress_repository = progress_repository
        self._runtime = runtime
        self._db_path = db_path

    def assign_course(
        self,
        company_id: str,
        user_id: int,
        course_slug: str,
    ) -> ManagerCourseAssignmentResult:
        """Assign one published course to one tenant member."""
        normalized_company_id = _validate_company_id(company_id)
        normalized_user_id = _validate_user_id(user_id)
        normalized_course_slug = _validate_course_slug(course_slug)

        member = self._team_service.get_member(
            normalized_company_id,
            normalized_user_id,
        )
        if member is None:
            return ManagerCourseAssignmentResult(
                success=False,
                code="member_not_found",
                message="Сотрудник не найден в компании.",
                user_id=normalized_user_id,
                course_slug=normalized_course_slug,
            )

        course = self._runtime.get_course(normalized_course_slug)
        if course is None:
            return ManagerCourseAssignmentResult(
                success=False,
                code="course_not_found",
                message="Курс не найден или недоступен.",
                user_id=normalized_user_id,
                course_slug=normalized_course_slug,
            )

        assigned = self._progress_repository.assign_course_to_user(
            self._db_path,
            member.user_id,
            course.slug,
        )
        if assigned:
            return ManagerCourseAssignmentResult(
                success=True,
                code="assigned",
                message="Курс назначен сотруднику.",
                user_id=member.user_id,
                course_slug=course.slug,
            )

        return ManagerCourseAssignmentResult(
            success=False,
            code="assignment_failed",
            message="Не удалось назначить курс.",
            user_id=member.user_id,
            course_slug=course.slug,
        )


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")

    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")

    return normalized


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")

    return user_id


def _validate_course_slug(course_slug: str) -> str:
    if not isinstance(course_slug, str):
        raise ValueError("course_slug must be a string")

    normalized = course_slug.strip()
    if not normalized:
        raise ValueError("course_slug must not be empty")

    return normalized
