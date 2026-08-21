"""Tests for manager team Web read models."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional

from app.repositories.company_team_repository import CompanyTeamMemberRecord
from app.web.manager_team_service import ManagerTeamService


class FakeCompanyTeamRepository:
    """Small repository fake for manager team service tests."""

    def __init__(
        self,
        records: tuple[CompanyTeamMemberRecord, ...],
    ) -> None:
        self.records = records
        self.calls: list[tuple[Path, str]] = []
        self.member_calls: list[tuple[Path, str, int]] = []

    def list_learning_summary(
        self,
        db_path: Path,
        company_id: str,
    ) -> tuple[CompanyTeamMemberRecord, ...]:
        self.calls.append((db_path, company_id))
        return self.records


    def get_learning_summary(
        self,
        db_path: Path,
        company_id: str,
        user_id: int,
    ) -> Optional[CompanyTeamMemberRecord]:
        self.member_calls.append((db_path, company_id, user_id))
        return next(
            (record for record in self.records if record.user_id == user_id),
            None,
        )


class ManagerTeamServiceTests(unittest.TestCase):
    """Verify manager team presentation behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "training.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_builds_member_view_model(self) -> None:
        repository = FakeCompanyTeamRepository(
            (
                CompanyTeamMemberRecord(
                    user_id=10,
                    username="alice",
                    first_name="Alice",
                    last_name="Smith",
                    role="student",
                    started_courses_count=3,
                    completed_courses_count=1,
                    average_progress_percent=58,
                ),
            )
        )
        service = ManagerTeamService(repository, self.db_path)

        members = service.get_team("company-a")

        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertEqual(member.user_id, 10)
        self.assertEqual(member.display_name, "Alice Smith")
        self.assertEqual(member.username, "alice")
        self.assertEqual(member.role, "student")
        self.assertEqual(member.role_label, "Сотрудник")
        self.assertEqual(member.started_courses_count, 3)
        self.assertEqual(member.completed_courses_count, 1)
        self.assertEqual(member.average_progress_percent, 58)
        self.assertEqual(
            repository.calls,
            [(self.db_path, "company-a")],
        )

    def test_display_name_falls_back_to_username(self) -> None:
        repository = FakeCompanyTeamRepository(
            (
                CompanyTeamMemberRecord(
                    user_id=11,
                    username="fallback-user",
                    first_name=None,
                    last_name="",
                    role="manager",
                    started_courses_count=0,
                    completed_courses_count=0,
                    average_progress_percent=0,
                ),
            )
        )
        service = ManagerTeamService(repository, self.db_path)

        member = service.get_team("company-a")[0]

        self.assertEqual(member.display_name, "fallback-user")
        self.assertEqual(member.role_label, "Менеджер")

    def test_display_name_falls_back_to_employee_id(self) -> None:
        repository = FakeCompanyTeamRepository(
            (
                CompanyTeamMemberRecord(
                    user_id=12,
                    username="   ",
                    first_name=None,
                    last_name=None,
                    role="admin",
                    started_courses_count=0,
                    completed_courses_count=0,
                    average_progress_percent=0,
                ),
            )
        )
        service = ManagerTeamService(repository, self.db_path)

        member = service.get_team("company-a")[0]

        self.assertEqual(member.display_name, "Сотрудник #12")
        self.assertIsNone(member.username)
        self.assertEqual(member.role_label, "Администратор")

    def test_company_id_is_normalized_before_repository_call(self) -> None:
        repository = FakeCompanyTeamRepository(())
        service = ManagerTeamService(repository, self.db_path)

        members = service.get_team("  company-a  ")

        self.assertEqual(members, ())
        self.assertEqual(
            repository.calls,
            [(self.db_path, "company-a")],
        )


    def test_get_member_returns_view_model(self) -> None:
        repository = FakeCompanyTeamRepository(
            (
                CompanyTeamMemberRecord(
                    user_id=20,
                    username="alice",
                    first_name="Alice",
                    last_name="Smith",
                    role="student",
                    started_courses_count=2,
                    completed_courses_count=1,
                    average_progress_percent=75,
                ),
            )
        )
        service = ManagerTeamService(repository, self.db_path)

        member = service.get_member("company-a", 20)

        self.assertIsNotNone(member)
        self.assertEqual(member.display_name, "Alice Smith")
        self.assertEqual(
            repository.member_calls,
            [(self.db_path, "company-a", 20)],
        )

    def test_get_member_returns_none_when_repository_hides_user(self) -> None:
        repository = FakeCompanyTeamRepository(())
        service = ManagerTeamService(repository, self.db_path)

        member = service.get_member("company-a", 99)

        self.assertIsNone(member)

    def test_get_member_rejects_invalid_user_id(self) -> None:
        repository = FakeCompanyTeamRepository(())
        service = ManagerTeamService(repository, self.db_path)

        with self.assertRaises(ValueError):
            service.get_member("company-a", 0)

        self.assertEqual(repository.member_calls, [])


    def test_empty_company_id_is_rejected(self) -> None:
        repository = FakeCompanyTeamRepository(())
        service = ManagerTeamService(repository, self.db_path)

        with self.assertRaises(ValueError):
            service.get_team("   ")

        self.assertEqual(repository.calls, [])


if __name__ == "__main__":
    unittest.main()
