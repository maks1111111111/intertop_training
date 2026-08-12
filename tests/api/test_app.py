"""Tests for the FastAPI application factory."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI

from app.api.app import create_app


class CreateAppTests(unittest.TestCase):
    """Verify the API application factory."""

    def test_create_app_returns_fastapi_application(self) -> None:
        application = create_app()
        self.assertIsInstance(application, FastAPI)

    @patch("app.api.app.load_project_env")
    def test_create_app_loads_project_env(self, mock_load_project_env) -> None:
        create_app()
        mock_load_project_env.assert_called_once_with()
