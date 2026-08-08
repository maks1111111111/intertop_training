"""Tests for the FastAPI application factory."""

from __future__ import annotations

import unittest

from fastapi import FastAPI

from app.api.app import create_app


class CreateAppTests(unittest.TestCase):
    """Verify the API application factory."""

    def test_create_app_returns_fastapi_application(self) -> None:
        application = create_app()
        self.assertIsInstance(application, FastAPI)
