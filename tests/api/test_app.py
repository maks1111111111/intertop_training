"""Tests for the FastAPI application factory."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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

    @patch("app.api.app.ContentRuntime")
    @patch("app.api.app.sync_courses")
    @patch("app.api.app.initialize_database")
    @patch("app.api.app.load_project_env")
    def test_create_app_syncs_courses_before_runtime_creation(
        self,
        mock_load_project_env,
        mock_initialize_database,
        mock_sync_courses,
        mock_content_runtime,
    ) -> None:
        lifecycle = MagicMock()
        lifecycle.attach_mock(mock_initialize_database, "initialize_database")
        lifecycle.attach_mock(mock_sync_courses, "sync_courses")
        lifecycle.attach_mock(mock_content_runtime, "content_runtime")

        create_app()

        project_root = Path(__file__).resolve().parents[2]
        db_path = project_root / "data" / "training.db"
        courses_dir = project_root / "courses"

        mock_load_project_env.assert_called_once_with()
        mock_initialize_database.assert_called_once_with(db_path)
        mock_sync_courses.assert_called_once_with(
            base_dir=courses_dir,
            db_path=db_path,
        )
        mock_content_runtime.assert_called_once_with(courses_dir)

        self.assertLess(
            lifecycle.mock_calls.index(
                call.initialize_database(db_path),
            ),
            lifecycle.mock_calls.index(
                call.sync_courses(
                    base_dir=courses_dir,
                    db_path=db_path,
                ),
            ),
        )
        self.assertLess(
            lifecycle.mock_calls.index(
                call.sync_courses(
                    base_dir=courses_dir,
                    db_path=db_path,
                ),
            ),
            lifecycle.mock_calls.index(
                call.content_runtime(courses_dir),
            ),
        )
