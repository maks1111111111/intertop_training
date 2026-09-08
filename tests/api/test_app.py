"""Tests for the FastAPI application factory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.app import create_app
from app.runtime_paths_config import RuntimePathsConfig
from app.web.csrf import SameOriginCSRFMiddleware
from app.web.security_headers import SecurityHeadersMiddleware


class CreateAppTests(unittest.TestCase):
    """Verify the API application factory."""

    def test_create_app_returns_fastapi_application(self) -> None:
        application = create_app()
        self.assertIsInstance(application, FastAPI)

    def test_create_app_enables_web_csrf_protection(self) -> None:
        application = create_app()

        self.assertTrue(
            any(
                middleware.cls is SameOriginCSRFMiddleware
                for middleware in application.user_middleware
            )
        )

    def test_create_app_enables_trusted_host_protection(self) -> None:
        application = create_app()

        self.assertTrue(
            any(
                middleware.cls is TrustedHostMiddleware
                for middleware in application.user_middleware
            )
        )

    def test_create_app_enables_security_headers(self) -> None:
        application = create_app()

        self.assertTrue(
            any(
                middleware.cls is SecurityHeadersMiddleware
                for middleware in application.user_middleware
            )
        )

    @patch("app.api.app.ContentRuntime")
    @patch("app.api.app.sync_courses")
    @patch("app.api.app.initialize_database")
    @patch("app.api.app.RuntimePathsConfig.from_environment")
    def test_create_app_uses_configured_runtime_paths(
        self,
        mock_from_environment,
        mock_initialize_database,
        mock_sync_courses,
        mock_content_runtime,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_root = Path(tmp) / "staging"
            runtime_paths = RuntimePathsConfig(
                db_path=staging_root / "data" / "training.db",
                courses_dir=staging_root / "courses",
                upload_dir=staging_root / "uploads",
            )
            mock_from_environment.return_value = runtime_paths

            application = create_app()

            mock_initialize_database.assert_called_once_with(runtime_paths.db_path)
            mock_sync_courses.assert_called_once_with(
                base_dir=runtime_paths.courses_dir,
                db_path=runtime_paths.db_path,
            )
            mock_content_runtime.assert_called_once_with(runtime_paths.courses_dir)
            self.assertEqual(application.state.db_path, runtime_paths.db_path)
            self.assertEqual(application.state.upload_dir, runtime_paths.upload_dir)
            self.assertIs(application.state.runtime_paths, runtime_paths)

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
