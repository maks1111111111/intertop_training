"""Tenant-scoped manager course assignment history for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.repositories.manager_course_assignment_repository import (
    ManagerCourseAssignmentRecord,
    ManagerCourseAssignmentRepository,
)

_STATUS_LABELS = {
    "assigned": "Назначен",
    "in_progress": "В процессе",
    "completed": "Завершён",
}


@dataclass(frozen=True)
class ManagerCourseAssignmentHistoryItem:
    """One explicit manager-authored course assignment for templates."""

    course_slug: str
    course_title: str
    status: str
    status_label: str
    progress_percent: int
    assigned_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


@dataclass(frozen=True)
class ManagerCourseAssignmentHistory:
    """Assignment lifecycle summary for one tenant-scoped employee."""

    assignments: tuple[ManagerCourseAssignmentHistoryItem, ...]
    total_count: int
    assigned_count: int
    in_progress_count: int
    completed_count: int


class ManagerCourseAssignmentHistoryService:
    """Build manager-facing assignment lifecycle view models."""

    def __init__(
        self,
        repository: ManagerCourseAssignmentRepository,
        db_path: Path,
    ) -> None:
        self._repository = repository
        self._db_path = db_path

    def get_for_member(
        self,
        company_id: str,
        user_id: int,
    ) -> ManagerCourseAssignmentHistory:
        """Return explicit manager-authored assignments for one employee."""
        normalized_company_id = _validate_company_id(company_id)
        normalized_user_id = _validate_user_id(user_id)

        records = self._repository.list_for_member(
            self._db_path,
            normalized_company_id,
            normalized_user_id,
        )
        assignments = tuple(_to_history_item(record) for record in records)

        assigned_count = sum(
            1 for item in assignments if item.status == "assigned"
        )
        in_progress_count = sum(
            1 for item in assignments if item.status == "in_progress"
        )
        completed_count = sum(
            1 for item in assignments if item.status == "completed"
        )

        return ManagerCourseAssignmentHistory(
            assignments=assignments,
            total_count=len(assignments),
            assigned_count=assigned_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
        )


def _to_history_item(
    record: ManagerCourseAssignmentRecord,
) -> ManagerCourseAssignmentHistoryItem:
    status_label = _STATUS_LABELS.get(record.status, record.status)

    return ManagerCourseAssignmentHistoryItem(
        course_slug=record.course_slug,
        course_title=record.course_title,
        status=record.status,
        status_label=status_label,
        progress_percent=record.progress_percent,
        assigned_at=record.assigned_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
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
