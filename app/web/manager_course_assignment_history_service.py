"""Tenant-scoped manager course assignment history for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from app.repositories.manager_course_assignment_repository import (
    ManagerCourseAssignmentRecord,
    ManagerCourseAssignmentRepository,
)

_STATUS_LABELS = {
    "assigned": "Назначен",
    "in_progress": "В процессе",
    "completed": "Завершён",
}

_DEVELOPMENT_SOURCE_LABELS = {
    "quiz": "Зона развития по тестам",
    "practical": "Зона развития по практическим заданиям",
}

_COMPLIANCE_STATUS_LABELS = {
    "no_deadline": "Без срока",
    "on_track": "В сроке",
    "due_soon": "Срок скоро",
    "overdue": "Просрочен",
    "completed_on_time": "Завершён в срок",
    "completed_late": "Завершён с опозданием",
}

_DUE_SOON_WINDOW = timedelta(hours=72)
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class ManagerCourseAssignmentHistoryItem:
    """One explicit manager-authored course assignment for templates."""

    course_slug: str
    course_title: str
    status: str
    status_label: str
    progress_percent: int
    assigned_at: str
    assigned_by_display_name: str
    due_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    compliance_status: str
    compliance_status_label: str
    development_source: Optional[str] = None
    development_source_label: Optional[str] = None
    development_reason: Optional[str] = None


@dataclass(frozen=True)
class ManagerCourseAssignmentHistory:
    """Assignment lifecycle summary for one tenant-scoped employee."""

    assignments: tuple[ManagerCourseAssignmentHistoryItem, ...]
    total_count: int
    assigned_count: int
    in_progress_count: int
    completed_count: int
    no_deadline_count: int
    on_track_count: int
    due_soon_count: int
    overdue_count: int
    completed_on_time_count: int
    completed_late_count: int


class ManagerCourseAssignmentHistoryService:
    """Build manager-facing assignment lifecycle view models."""

    def __init__(
        self,
        repository: ManagerCourseAssignmentRepository,
        db_path: Path,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._repository = repository
        self._db_path = db_path
        self._now_provider = now_provider

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
        now = self._now_provider()
        assignments = tuple(_to_history_item(record, now) for record in records)

        assigned_count = sum(
            1 for item in assignments if item.status == "assigned"
        )
        in_progress_count = sum(
            1 for item in assignments if item.status == "in_progress"
        )
        completed_count = sum(
            1 for item in assignments if item.status == "completed"
        )
        no_deadline_count = sum(
            1 for item in assignments if item.compliance_status == "no_deadline"
        )
        on_track_count = sum(
            1 for item in assignments if item.compliance_status == "on_track"
        )
        due_soon_count = sum(
            1 for item in assignments if item.compliance_status == "due_soon"
        )
        overdue_count = sum(
            1 for item in assignments if item.compliance_status == "overdue"
        )
        completed_on_time_count = sum(
            1
            for item in assignments
            if item.compliance_status == "completed_on_time"
        )
        completed_late_count = sum(
            1 for item in assignments if item.compliance_status == "completed_late"
        )

        return ManagerCourseAssignmentHistory(
            assignments=assignments,
            total_count=len(assignments),
            assigned_count=assigned_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            no_deadline_count=no_deadline_count,
            on_track_count=on_track_count,
            due_soon_count=due_soon_count,
            overdue_count=overdue_count,
            completed_on_time_count=completed_on_time_count,
            completed_late_count=completed_late_count,
        )


def _to_history_item(
    record: ManagerCourseAssignmentRecord,
    now: datetime,
) -> ManagerCourseAssignmentHistoryItem:
    status_label = _STATUS_LABELS.get(record.status, record.status)
    compliance_status, compliance_status_label = _classify_compliance(
        record.status,
        record.due_at,
        record.completed_at,
        now,
    )

    return ManagerCourseAssignmentHistoryItem(
        course_slug=record.course_slug,
        course_title=record.course_title,
        status=record.status,
        status_label=status_label,
        progress_percent=record.progress_percent,
        assigned_at=record.assigned_at,
        assigned_by_display_name=_assigned_by_display_name(record),
        due_at=record.due_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        compliance_status=compliance_status,
        compliance_status_label=compliance_status_label,
        development_source=record.development_source,
        development_source_label=_development_source_label(record.development_source),
        development_reason=record.development_reason,
    )


def _classify_compliance(
    status: str,
    due_at: Optional[str],
    completed_at: Optional[str],
    now: datetime,
) -> tuple[str, str]:
    if due_at is None:
        return _compliance_result("no_deadline")

    due_datetime = _parse_timestamp(due_at)
    if due_datetime is None:
        return _compliance_result("no_deadline")

    if status == "completed":
        completed_datetime = _parse_timestamp(completed_at)
        if completed_datetime is not None:
            if completed_datetime <= due_datetime:
                return _compliance_result("completed_on_time")
            return _compliance_result("completed_late")

        return _classify_active_compliance(due_datetime, now)

    return _classify_active_compliance(due_datetime, now)


def _classify_active_compliance(
    due_datetime: datetime,
    now: datetime,
) -> tuple[str, str]:
    if now > due_datetime:
        return _compliance_result("overdue")
    if due_datetime - now <= _DUE_SOON_WINDOW:
        return _compliance_result("due_soon")
    return _compliance_result("on_track")


def _compliance_result(status: str) -> tuple[str, str]:
    return status, _COMPLIANCE_STATUS_LABELS[status]


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        return datetime.strptime(normalized, _TIMESTAMP_FORMAT)
    except ValueError:
        return None


def _development_source_label(development_source: Optional[str]) -> Optional[str]:
    if development_source is None:
        return None

    return _DEVELOPMENT_SOURCE_LABELS.get(development_source)


def _assigned_by_display_name(record: ManagerCourseAssignmentRecord) -> str:
    name_parts = tuple(
        value
        for value in (
            _normalize_optional_text(record.assigned_by_first_name),
            _normalize_optional_text(record.assigned_by_last_name),
        )
        if value
    )
    if name_parts:
        return " ".join(name_parts)

    username = _normalize_optional_text(record.assigned_by_username)
    if username:
        return username

    return f"Пользователь #{record.assigned_by_user_id}"


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    return normalized


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
