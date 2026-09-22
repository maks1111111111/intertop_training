"""Tests for owner-only authenticator codes."""

from __future__ import annotations

import unittest

from app.web.platform_owner_totp import PlatformOwnerTOTP


class PlatformOwnerTOTPTests(unittest.TestCase):
    def setUp(self) -> None:
        # RFC 6238 SHA-1 test secret: 20 ASCII bytes encoded as Base32.
        self.totp = PlatformOwnerTOTP.from_environment(
            {
                "INTERTOP_PLATFORM_OWNER_TOTP_SECRET": (
                    "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
                )
            }
        )

    def test_accepts_current_and_adjacent_time_steps(self) -> None:
        self.assertTrue(self.totp.verify("287082", at_time=59))
        self.assertTrue(self.totp.verify("287082", at_time=60))

    def test_rejects_invalid_code(self) -> None:
        self.assertFalse(self.totp.verify("000000", at_time=59))
        self.assertFalse(self.totp.verify("not-a-code", at_time=59))

    def test_missing_environment_secret_disables_mfa(self) -> None:
        service = PlatformOwnerTOTP.from_environment({})
        self.assertFalse(service.is_configured)
        self.assertFalse(service.verify("287082", at_time=59))

    def test_rejects_short_or_malformed_secret(self) -> None:
        with self.assertRaises(ValueError):
            PlatformOwnerTOTP.from_environment(
                {"INTERTOP_PLATFORM_OWNER_TOTP_SECRET": "invalid!"}
            )
        with self.assertRaises(ValueError):
            PlatformOwnerTOTP.from_environment(
                {"INTERTOP_PLATFORM_OWNER_TOTP_SECRET": "MZXW6"}
            )
