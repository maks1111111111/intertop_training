"""Manager team read model for the Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.repositories.company_team_repository import (
    CompanyTeamMemberRecord,
    CompanyTeamRepository,
)


_ROLE_LABELS = {
    "student": "Сотрудник",
    "manager": "Менеджер",
    "admin": "Администратор",
}


@dataclass(frozen=True)
class ManagerTeamMember:
    """One member row on the manager team page."""

    user_id: int
    display_name: str
    username: Optional[str]
    role: str
    role_label: str
    started_courses_count: int
    completed_courses_count: int
    average_progress_percent: int


class ManagerTeamService:
    """Build tenant-scoped manager team view models."""

    def __init__(
        self,
        repository: CompanyTeamRepository,
        db_path: Path,
    ) -> None:
        self._repository = repository
        self._db_path = db_path

    def get_team(
        self,
        company_id: str,
    ) -> tuple[ManagerTeamMember, ...]:
        """Return active members for one resolved tenant."""
        normalized_company_id = _validate_company_id(company_id)
        records = self._repository.list_learning_summary(
            self._db_path,
            normalized_company_id,
        )

        return tuple(_to_view_model(record) for record in records)


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")

    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")

    return normalized


def _to_view_model(
    record: CompanyTeamMemberRecord,
) -> ManagerTeamMember:
    return ManagerTeamMember(
        user_id=record.user_id,
        display_name=_display_name(record),
        username=_normalize_optional_text(record.username),
        role=record.role,
        role_label=_role_label(record.role),
        started_courses_count=record.started_courses_count,
        completed_courses_count=record.completed_courses_count,
        average_progress_percent=record.average_progress_percent,
    )


def _display_name(record: CompanyTeamMemberRecord) -> str:
    name_parts = tuple(
        value
        for value in (
            _normalize_optional_text(record.first_name),
            _normalize_optional_text(record.last_name),
        )
        if value
    )
    if name_parts:
        return " ".join(name_parts)

    username = _normalize_optional_text(record.username)
    if username:
        return username

    return f"Сотрудник #{record.user_id}"


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    return normalized


def _role_label(role: str) -> str:
    normalized = role.strip().lower()
    return _ROLE_LABELS.get(normalized, normalized)
