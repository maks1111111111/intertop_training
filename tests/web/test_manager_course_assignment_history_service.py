"""Tests for tenant-scoped manager course assignment history service."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Optional

from app.repositories.manager_course_assignment_repository import (
    ManagerCourseAssignmentRecord,
)
from app.web.manager_course_assignment_history_service import (
    ManagerCourseAssignmentHistory,
    ManagerCourseAssignmentHistoryItem,
    ManagerCourseAssignmentHistoryService,
)


class FakeManagerCourseAssignmentRepository:
    def __init__(
        self,
        records: tuple[ManagerCourseAssignmentRecord, ...] = (),
    ) -> None:
        self.records = records
        self.calls: list[tuple[Path, str, int]] = []

    def list_for_member(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
    ) -> tuple[ManagerCourseAssignmentRecord, ...]:
        self.calls.append((db_path, company_id, user_id))
        return self.records


class ManagerCourseAssignmentHistoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path("/tmp/training.db")
        self.repository = FakeManagerCourseAssignmentRepository()
        self.service = ManagerCourseAssignmentHistoryService(
            self.repository,
            self.db_path,
        )

    def _record(
        self,
        *,
        course_slug: str,
        course_title: str,
        status: str,
        progress_percent: int,
        assigned_at: str,
        assigned_by_user_id: int = 1,
        assigned_by_username: Optional[str] = "manager",
        assigned_by_first_name: Optional[str] = "Anna",
        assigned_by_last_name: Optional[str] = "Manager",
        due_at: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> ManagerCourseAssignmentRecord:
        return ManagerCourseAssignmentRecord(
            employee_user_id=2,
            course_slug=course_slug,
            course_title=course_title,
            status=status,
            progress_percent=progress_percent,
            assigned_at=assigned_at,
            assigned_by_user_id=assigned_by_user_id,
            assigned_by_username=assigned_by_username,
            assigned_by_first_name=assigned_by_first_name,
            assigned_by_last_name=assigned_by_last_name,
            due_at=due_at,
            started_at=started_at,
            completed_at=completed_at,
        )

    def test_maps_assigned_in_progress_and_completed_statuses(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="alpha",
                course_title="Alpha Course",
                status="assigned",
                progress_percent=0,
                assigned_at="2026-08-31 10:00:00",
            ),
            self._record(
                course_slug="beta",
                course_title="Beta Course",
                status="in_progress",
                progress_percent=60,
                assigned_at="2026-08-31 11:00:00",
                started_at="2026-08-31 12:00:00",
            ),
            self._record(
                course_slug="gamma",
                course_title="Gamma Course",
                status="completed",
                progress_percent=100,
                assigned_at="2026-08-31 13:00:00",
                started_at="2026-08-31 14:00:00",
                completed_at="2026-08-31 15:00:00",
            ),
        )

        history = self.service.get_for_member(" intertop ", 2)

        self.assertEqual(
            history,
            ManagerCourseAssignmentHistory(
                assignments=(
                    ManagerCourseAssignmentHistoryItem(
                        course_slug="alpha",
                        course_title="Alpha Course",
                        status="assigned",
                        status_label="Назначен",
                        progress_percent=0,
                        assigned_at="2026-08-31 10:00:00",
                        assigned_by_display_name="Anna Manager",
                        started_at=None,
                        completed_at=None,
                    ),
                    ManagerCourseAssignmentHistoryItem(
                        course_slug="beta",
                        course_title="Beta Course",
                        status="in_progress",
                        status_label="В процессе",
                        progress_percent=60,
                        assigned_at="2026-08-31 11:00:00",
                        assigned_by_display_name="Anna Manager",
                        started_at="2026-08-31 12:00:00",
                        completed_at=None,
                    ),
                    ManagerCourseAssignmentHistoryItem(
                        course_slug="gamma",
                        course_title="Gamma Course",
                        status="completed",
                        status_label="Завершён",
                        progress_percent=100,
                        assigned_at="2026-08-31 13:00:00",
                        assigned_by_display_name="Anna Manager",
                        started_at="2026-08-31 14:00:00",
                        completed_at="2026-08-31 15:00:00",
                    ),
                ),
                total_count=3,
                assigned_count=1,
                in_progress_count=1,
                completed_count=1,
            ),
        )
        self.assertEqual(
            self.repository.calls,
            [(self.db_path, "intertop", 2)],
        )

    def test_unknown_status_uses_raw_status_as_label(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="legacy",
                course_title="Legacy Course",
                status="archived",
                progress_percent=10,
                assigned_at="2026-08-31 10:00:00",
            ),
        )

        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(history.assignments[0].status_label, "archived")
        self.assertEqual(history.total_count, 1)
        self.assertEqual(history.assigned_count, 0)
        self.assertEqual(history.in_progress_count, 0)
        self.assertEqual(history.completed_count, 0)

    def test_empty_history(self) -> None:
        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(
            history,
            ManagerCourseAssignmentHistory(
                assignments=(),
                total_count=0,
                assigned_count=0,
                in_progress_count=0,
                completed_count=0,
            ),
        )

    def test_invalid_company_id_rejected(self) -> None:
        for invalid in ("", "   ", 123, None):
            with self.subTest(company_id=invalid):
                with self.assertRaises(ValueError):
                    self.service.get_for_member(invalid, 2)  # type: ignore[arg-type]

        self.assertEqual(self.repository.calls, [])

    def test_invalid_user_id_rejected(self) -> None:
        for invalid in (0, -1, True, "2", None):
            with self.subTest(user_id=invalid):
                with self.assertRaises(ValueError):
                    self.service.get_for_member("intertop", invalid)  # type: ignore[arg-type]

        self.assertEqual(self.repository.calls, [])

    def test_assigned_by_display_name_uses_first_and_last_name(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="alpha",
                course_title="Alpha Course",
                status="assigned",
                progress_percent=0,
                assigned_at="2026-08-31 10:00:00",
                assigned_by_first_name="  Ivan  ",
                assigned_by_last_name="  Petrov ",
            ),
        )

        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(
            history.assignments[0].assigned_by_display_name,
            "Ivan Petrov",
        )

    def test_assigned_by_display_name_uses_first_name_only(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="alpha",
                course_title="Alpha Course",
                status="assigned",
                progress_percent=0,
                assigned_at="2026-08-31 10:00:00",
                assigned_by_first_name="Maria",
                assigned_by_last_name=None,
            ),
        )

        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(history.assignments[0].assigned_by_display_name, "Maria")

    def test_assigned_by_display_name_uses_last_name_only(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="alpha",
                course_title="Alpha Course",
                status="assigned",
                progress_percent=0,
                assigned_at="2026-08-31 10:00:00",
                assigned_by_first_name=None,
                assigned_by_last_name="Sokolov",
            ),
        )

        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(history.assignments[0].assigned_by_display_name, "Sokolov")

    def test_assigned_by_display_name_uses_username_fallback(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="alpha",
                course_title="Alpha Course",
                status="assigned",
                progress_percent=0,
                assigned_at="2026-08-31 10:00:00",
                assigned_by_username="  team-lead  ",
                assigned_by_first_name=None,
                assigned_by_last_name=None,
            ),
        )

        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(history.assignments[0].assigned_by_display_name, "team-lead")

    def test_assigned_by_display_name_uses_user_id_fallback(self) -> None:
        self.repository.records = (
            self._record(
                course_slug="alpha",
                course_title="Alpha Course",
                status="assigned",
                progress_percent=0,
                assigned_at="2026-08-31 10:00:00",
                assigned_by_user_id=42,
                assigned_by_username=None,
                assigned_by_first_name=None,
                assigned_by_last_name=None,
            ),
        )

        history = self.service.get_for_member("intertop", 2)

        self.assertEqual(
            history.assignments[0].assigned_by_display_name,
            "Пользователь #42",
        )


if __name__ == "__main__":
    unittest.main()
