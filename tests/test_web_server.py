"""Tests for the production Web server entry point."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.web_server import WebServerConfig, main


class WebServerConfigTests(unittest.TestCase):
    def test_defaults_bind_to_loopback_and_trust_local_proxy(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = WebServerConfig.from_environment()

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8000)
        self.assertEqual(config.forwarded_allow_ips, "127.0.0.1")

    def test_reads_network_settings_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_WEB_HOST": "10.0.0.5",
                "INTERTOP_WEB_PORT": "8080",
                "INTERTOP_FORWARDED_ALLOW_IPS": "10.0.0.1,10.0.0.2",
            },
            clear=True,
        ):
            config = WebServerConfig.from_environment()

        self.assertEqual(config.host, "10.0.0.5")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.forwarded_allow_ips, "10.0.0.1,10.0.0.2")

    def test_rejects_invalid_port(self) -> None:
        with patch.dict(os.environ, {"INTERTOP_WEB_PORT": "70000"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "between 1 and 65535"):
                WebServerConfig.from_environment()

    def test_rejects_wildcard_proxy_trust(self) -> None:
        with patch.dict(
            os.environ,
            {"INTERTOP_FORWARDED_ALLOW_IPS": "*"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "not '\\*'"):
                WebServerConfig.from_environment()


class WebServerMainTests(unittest.TestCase):
    @patch("app.web_server.uvicorn.run")
    @patch("app.web_server.WebServerConfig.from_environment")
    @patch("app.web_server.load_project_env")
    def test_main_runs_one_hardened_proxy_aware_worker(
        self,
        mock_load_project_env,
        mock_from_environment,
        mock_run,
    ) -> None:
        mock_from_environment.return_value = WebServerConfig(
            host="127.0.0.1",
            port=9000,
            forwarded_allow_ips="10.0.0.1",
        )

        main()

        mock_load_project_env.assert_called_once_with()
        mock_run.assert_called_once_with(
            "app.api.app:app",
            host="127.0.0.1",
            port=9000,
            workers=1,
            proxy_headers=True,
            forwarded_allow_ips="10.0.0.1",
            server_header=False,
        )
