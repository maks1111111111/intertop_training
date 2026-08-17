"""Tests for signed canonical Web sessions."""

from __future__ import annotations

import base64
import json
import unittest

from app.web.web_session_service import (
    DEFAULT_SESSION_TTL_SECONDS,
    WebSession,
    WebSessionService,
)


SECRET = "test-session-secret-key-with-at-least-32-bytes"


def _decode_payload(token: str) -> dict:
    encoded_payload = token.split(".", 1)[0]
    padding = "=" * (-len(encoded_payload) % 4)
    raw = base64.urlsafe_b64decode(
        (encoded_payload + padding).encode("ascii")
    )
    return json.loads(raw.decode("utf-8"))


class WebSessionServiceTests(unittest.TestCase):
    def test_round_trip_returns_canonical_identity(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        token = service.create_token(
            user_id=42,
            company_id="intertop",
        )
        session = service.resolve_token(token)

        self.assertIsInstance(session, WebSession)
        assert session is not None
        self.assertEqual(session.user_id, 42)
        self.assertEqual(session.company_id, "intertop")
        self.assertEqual(session.issued_at, 1_000)
        self.assertEqual(
            session.expires_at,
            1_000 + DEFAULT_SESSION_TTL_SECONDS,
        )

    def test_company_id_is_normalized(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        token = service.create_token(
            user_id=42,
            company_id="  intertop  ",
        )
        session = service.resolve_token(token)

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.company_id, "intertop")

    def test_password_only_identity_does_not_require_telegram_id(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        token = service.create_token(
            user_id=123,
            company_id="company-a",
        )
        payload = _decode_payload(token)

        self.assertEqual(payload["user_id"], 123)
        self.assertEqual(payload["company_id"], "company-a")
        self.assertNotIn("telegram_id", payload)

    def test_expired_token_is_rejected(self) -> None:
        now = [1_000]
        service = WebSessionService(
            SECRET,
            ttl_seconds=60,
            clock=lambda: now[0],
        )

        token = service.create_token(
            user_id=42,
            company_id="intertop",
        )

        now[0] = 1_060

        self.assertIsNone(service.resolve_token(token))

    def test_token_is_valid_immediately_before_expiry(self) -> None:
        now = [1_000]
        service = WebSessionService(
            SECRET,
            ttl_seconds=60,
            clock=lambda: now[0],
        )

        token = service.create_token(
            user_id=42,
            company_id="intertop",
        )

        now[0] = 1_059

        self.assertIsNotNone(service.resolve_token(token))

    def test_tampered_payload_is_rejected(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        token = service.create_token(
            user_id=42,
            company_id="intertop",
        )
        encoded_payload, signature = token.split(".")

        payload = _decode_payload(token)
        payload["user_id"] = 999

        raw = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        tampered_payload = (
            base64.urlsafe_b64encode(raw)
            .decode("ascii")
            .rstrip("=")
        )

        tampered_token = f"{tampered_payload}.{signature}"

        self.assertNotEqual(tampered_payload, encoded_payload)
        self.assertIsNone(service.resolve_token(tampered_token))

    def test_tampered_signature_is_rejected(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        token = service.create_token(
            user_id=42,
            company_id="intertop",
        )
        payload, signature = token.split(".")

        replacement = "A" if signature[-1] != "A" else "B"
        tampered = f"{payload}.{signature[:-1]}{replacement}"

        self.assertIsNone(service.resolve_token(tampered))

    def test_token_signed_by_another_secret_is_rejected(self) -> None:
        first = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )
        second = WebSessionService(
            "another-session-secret-key-with-at-least-32-bytes",
            clock=lambda: 1_000,
        )

        token = first.create_token(
            user_id=42,
            company_id="intertop",
        )

        self.assertIsNone(second.resolve_token(token))

    def test_malformed_tokens_are_rejected(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        for token in (
            "",
            ".",
            "abc",
            "abc.",
            ".abc",
            "a.b.c",
            "%%%.$$$",
        ):
            with self.subTest(token=token):
                self.assertIsNone(service.resolve_token(token))

    def test_invalid_user_ids_are_rejected_on_create(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    service.create_token(
                        user_id=invalid,  # type: ignore[arg-type]
                        company_id="intertop",
                    )

    def test_invalid_company_ids_are_rejected_on_create(self) -> None:
        service = WebSessionService(
            SECRET,
            clock=lambda: 1_000,
        )

        for invalid in ("", "   ", None, 123):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    service.create_token(
                        user_id=42,
                        company_id=invalid,  # type: ignore[arg-type]
                    )

    def test_short_secret_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            WebSessionService("too-short")

    def test_invalid_ttl_is_rejected(self) -> None:
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    WebSessionService(
                        SECRET,
                        ttl_seconds=invalid,  # type: ignore[arg-type]
                    )

    def test_future_issued_token_is_rejected(self) -> None:
        now = [1_000]
        service = WebSessionService(
            SECRET,
            ttl_seconds=60,
            clock=lambda: now[0],
        )

        now[0] = 1_100
        token = service.create_token(
            user_id=42,
            company_id="intertop",
        )

        now[0] = 1_000

        self.assertIsNone(service.resolve_token(token))


if __name__ == "__main__":
    unittest.main()
