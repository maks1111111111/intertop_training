"""Tests for Web session environment configuration."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.web.web_session_config import WebSessionConfig


class WebSessionConfigTests(unittest.TestCase):
    """Verify secure fail-closed Web session configuration."""

    @patch.dict(
        os.environ,
        {
            "WEB_SESSION_SECRET": "a-secure-session-secret-with-32-plus-bytes",
        },
        clear=True,
    )
    def test_from_environment_reads_secret(self) -> None:
        config = WebSessionConfig.from_environment()

        self.assertEqual(
            config.secret_key,
            "a-secure-session-secret-with-32-plus-bytes",
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_secret_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            WebSessionConfig.from_environment()

        self.assertEqual(
            str(context.exception),
            "WEB_SESSION_SECRET environment variable is not set.",
        )

    @patch.dict(
        os.environ,
        {"WEB_SESSION_SECRET": ""},
        clear=True,
    )
    def test_empty_secret_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            WebSessionConfig.from_environment()

        self.assertEqual(
            str(context.exception),
            "WEB_SESSION_SECRET environment variable must not be empty.",
        )

    @patch.dict(
        os.environ,
        {"WEB_SESSION_SECRET": "    "},
        clear=True,
    )
    def test_whitespace_only_secret_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            WebSessionConfig.from_environment()

        self.assertEqual(
            str(context.exception),
            "WEB_SESSION_SECRET environment variable must not be empty.",
        )

    @patch.dict(
        os.environ,
        {"WEB_SESSION_SECRET": "too-short"},
        clear=True,
    )
    def test_short_secret_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            WebSessionConfig.from_environment()

        self.assertEqual(
            str(context.exception),
            "WEB_SESSION_SECRET environment variable must contain at least 32 bytes.",
        )

    @patch.dict(
        os.environ,
        {"WEB_SESSION_SECRET": "я" * 16},
        clear=True,
    )
    def test_secret_length_is_measured_in_bytes(self) -> None:
        config = WebSessionConfig.from_environment()

        self.assertEqual(config.secret_key, "я" * 16)


if __name__ == "__main__":
    unittest.main()
