"""Tests for explicit, least-privilege platform support grants."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.repositories.company_repository import CompanyRepository
from app.repositories.platform_admin_repository import PlatformAdminRepository
from app.repositories.platform_support_access_repository import (
    PlatformSupportAccessRepository,
)
from app.services.platform_support_access_service import (
    PlatformSupportAccessError,
    PlatformSupportAccessService,
)


class PlatformSupportAccessServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        self.now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
        self.admins = PlatformAdminRepository()
        self.owner_id = self._create_user("owner")
        self.operator_id = self._create_user("operator")
        self.other_operator_id = self._create_user("other-operator")
        self.admins.bootstrap_owner(self.db_path, self.owner_id)
        self.admins.grant_admin(self.db_path, self.operator_id)
        self.admins.grant_admin(self.db_path, self.other_operator_id)
        CompanyRepository().create(self.db_path, "company-a", "Company A")
        CompanyRepository().create(self.db_path, "company-b", "Company B")
        self.service = PlatformSupportAccessService(
            PlatformSupportAccessRepository(),
            self.admins,
            CompanyRepository(),
            clock=lambda: self.now,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_user(self, username: str) -> int:
        with get_connection(self.db_path) as connection:
            return int(connection.execute("INSERT INTO users (username) VALUES (?)", (username,)).lastrowid)

    def test_grant_is_bound_to_one_operator_company_reason_and_expiry(self) -> None:
        access = self.service.grant(self.db_path, actor_user_id=self.owner_id, operator_user_id=self.operator_id, company_id="company-a", reason="Investigate ticket INC-1", duration_minutes=15)

        self.assertEqual(access.operator_user_id, self.operator_id)
        self.assertEqual(access.company_id, "company-a")
        self.assertEqual(access.expires_at, self.now + timedelta(minutes=15))
        self.assertEqual(self.service.resolve_for_operator(self.db_path, access_id=access.id, operator_user_id=self.operator_id), access)
        self.assertIsNone(self.service.resolve_for_operator(self.db_path, access_id=access.id, operator_user_id=self.owner_id))
        self.assertEqual(
            [event.action for event in self.admins.list_audit_events(self.db_path)[:2]],
            [
                "support_access.read_only_diagnostics_viewed",
                "support_access.granted",
            ],
        )

    def test_access_expires_and_can_be_revoked_immediately(self) -> None:
        access = self.service.grant(self.db_path, actor_user_id=self.owner_id, operator_user_id=self.operator_id, company_id="company-a", reason="Investigate ticket INC-2", duration_minutes=5)
        self.now += timedelta(minutes=5)
        self.assertIsNone(self.service.resolve_for_operator(self.db_path, access_id=access.id, operator_user_id=self.operator_id))

        self.now -= timedelta(minutes=5)
        self.service.revoke(self.db_path, actor_user_id=self.owner_id, access_id=access.id, reason="Incident resolved")
        self.assertIsNone(self.service.resolve_for_operator(self.db_path, access_id=access.id, operator_user_id=self.operator_id))
        self.assertEqual(self.admins.list_audit_events(self.db_path)[0].action, "support_access.revoked")

    def test_owner_and_duration_rules_are_enforced(self) -> None:
        with self.assertRaisesRegex(PlatformSupportAccessError, "owner access"):
            self.service.grant(self.db_path, actor_user_id=self.operator_id, operator_user_id=self.operator_id, company_id="company-a", reason="Unauthorized", duration_minutes=5)
        with self.assertRaisesRegex(PlatformSupportAccessError, "between 5 and 60"):
            self.service.grant(self.db_path, actor_user_id=self.owner_id, operator_user_id=self.operator_id, company_id="company-a", reason="Too long", duration_minutes=61)

    def test_operator_lists_only_its_own_active_support_windows(self) -> None:
        mine = self.service.grant(self.db_path, actor_user_id=self.owner_id, operator_user_id=self.operator_id, company_id="company-a", reason="My ticket", duration_minutes=15)
        self.service.grant(self.db_path, actor_user_id=self.owner_id, operator_user_id=self.other_operator_id, company_id="company-b", reason="Other ticket", duration_minutes=15)

        self.assertEqual(
            self.service.list_active_for_operator(
                self.db_path,
                operator_user_id=self.operator_id,
            ),
            (mine,),
        )

    def test_deactivated_company_cannot_receive_or_use_support_access(self) -> None:
        access = self.service.grant(
            self.db_path,
            actor_user_id=self.owner_id,
            operator_user_id=self.operator_id,
            company_id="company-a",
            reason="Active incident",
            duration_minutes=15,
        )
        CompanyRepository().set_active(self.db_path, "company-a", False)

        self.assertIsNone(
            self.service.resolve_for_operator(
                self.db_path,
                access_id=access.id,
                operator_user_id=self.operator_id,
            )
        )
        self.assertEqual(
            self.service.list_active_for_operator(
                self.db_path,
                operator_user_id=self.operator_id,
            ),
            (),
        )
        with self.assertRaisesRegex(PlatformSupportAccessError, "must be active"):
            self.service.grant(
                self.db_path,
                actor_user_id=self.owner_id,
                operator_user_id=self.operator_id,
                company_id="company-a",
                reason="Inactive incident",
                duration_minutes=15,
            )


if __name__ == "__main__":
    unittest.main()
