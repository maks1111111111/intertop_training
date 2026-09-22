"""Bounded in-memory protection for public password login endpoints."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Tuple


@dataclass(frozen=True)
class LoginAttemptDecision:
    """Describe whether a login attempt may proceed."""

    allowed: bool
    retry_after_seconds: int = 0


class LoginAttemptGuard:
    """Limit failed logins by client and client/account pair.

    The account identifier is hashed before it becomes an in-memory key. Limits
    reset on process restart and successful authentication; this deliberately
    avoids persistent account lockouts while still slowing automated attacks.
    """

    def __init__(
        self,
        *,
        account_failures: int = 5,
        client_failures: int = 20,
        window_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if account_failures < 1 or client_failures < 1 or window_seconds < 1:
            raise ValueError("login attempt limits must be positive")
        self._account_failures = account_failures
        self._client_failures = client_failures
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        *,
        scope: str,
        client_address: str,
        account_identifier: str,
    ) -> LoginAttemptDecision:
        """Return a retry delay when either bounded failure bucket is full."""
        now = self._clock()
        buckets = self._bucket_keys(scope, client_address, account_identifier)
        with self._lock:
            account_events = self._active_events(buckets[0], now)
            client_events = self._active_events(buckets[1], now)
            retry_after = max(
                self._retry_after(account_events, self._account_failures, now),
                self._retry_after(client_events, self._client_failures, now),
            )
        return LoginAttemptDecision(
            allowed=retry_after == 0,
            retry_after_seconds=retry_after,
        )

    def record_failure(
        self,
        *,
        scope: str,
        client_address: str,
        account_identifier: str,
    ) -> None:
        """Count one failed authentication in both relevant buckets."""
        now = self._clock()
        buckets = self._bucket_keys(scope, client_address, account_identifier)
        with self._lock:
            for key in buckets:
                self._active_events(key, now).append(now)

    def record_success(
        self,
        *,
        scope: str,
        client_address: str,
        account_identifier: str,
    ) -> None:
        """Clear failures for a successfully authenticated client/account pair."""
        buckets = self._bucket_keys(scope, client_address, account_identifier)
        with self._lock:
            for key in buckets:
                self._events.pop(key, None)

    def _bucket_keys(
        self,
        scope: str,
        client_address: str,
        account_identifier: str,
    ) -> Tuple[str, str]:
        normalized_scope = scope.strip().casefold()
        normalized_client = client_address.strip().casefold() or "unknown"
        normalized_account = account_identifier.strip().casefold()
        account_digest = hashlib.sha256(normalized_account.encode("utf-8")).hexdigest()
        return (
            f"account:{normalized_scope}:{normalized_client}:{account_digest}",
            f"client:{normalized_scope}:{normalized_client}",
        )

    def _active_events(self, key: str, now: float) -> Deque[float]:
        events = self._events.setdefault(key, deque())
        cutoff = now - self._window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            # Keep the deque for the caller, but old empty buckets are replaced
            # naturally whenever their key is used again.
            self._events[key] = events
        return events

    def _retry_after(self, events: Deque[float], limit: int, now: float) -> int:
        if len(events) < limit:
            return 0
        return max(1, math.ceil(events[0] + self._window_seconds - now))
