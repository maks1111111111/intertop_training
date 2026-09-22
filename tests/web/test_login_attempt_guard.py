"""Tests for bounded password-login attempt tracking."""

from __future__ import annotations

import unittest

from app.web.login_attempt_guard import LoginAttemptGuard


class LoginAttemptGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1000.0
        self.guard = LoginAttemptGuard(
            account_failures=2,
            client_failures=4,
            window_seconds=60,
            clock=lambda: self.now,
        )

    def _decision(self, account: str = "user@example.com"):
        return self.guard.check(
            scope="tenant",
            client_address="203.0.113.10",
            account_identifier=account,
        )

    def _failure(self, account: str = "user@example.com") -> None:
        self.guard.record_failure(
            scope="tenant",
            client_address="203.0.113.10",
            account_identifier=account,
        )

    def test_account_pair_is_blocked_after_bounded_failures(self) -> None:
        self._failure()
        self._failure()

        decision = self._decision()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.retry_after_seconds, 60)

    def test_client_bucket_combines_failures_for_different_accounts(self) -> None:
        for account in ("a@example.com", "b@example.com"):
            self._failure(account)
            self._failure(account)

        decision = self._decision("new@example.com")

        self.assertFalse(decision.allowed)

    def test_window_expiry_allows_a_new_attempt(self) -> None:
        self._failure()
        self._failure()
        self.now += 61

        self.assertTrue(self._decision().allowed)

    def test_success_clears_relevant_failure_buckets(self) -> None:
        self._failure()
        self.guard.record_success(
            scope="tenant",
            client_address="203.0.113.10",
            account_identifier="user@example.com",
        )

        self.assertTrue(self._decision().allowed)


if __name__ == "__main__":
    unittest.main()
