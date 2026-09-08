"""Tests for environment-isolated runtime paths."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.runtime_paths_config import RuntimePathsConfig


_PATH_ENV_NAMES = (
    "INTERTOP_DB_PATH",
    "INTERTOP_COURSES_DIR",
    "INTERTOP_UPLOAD_DIR",
)


class RuntimePathsConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp.name) / "project"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _environment_without_runtime_paths(self) -> dict[str, str]:
        return {
            key: value
            for key, value in os.environ.items()
            if key not in _PATH_ENV_NAMES
        }

    def test_defaults_keep_local_project_layout(self) -> None:
        with patch.dict(
            os.environ,
            self._environment_without_runtime_paths(),
            clear=True,
        ):
            config = RuntimePathsConfig.from_environment(
                project_root=self.project_root,
            )

        self.assertEqual(
            config.db_path,
            (self.project_root / "data" / "training.db").resolve(),
        )
        self.assertEqual(
            config.courses_dir,
            (self.project_root / "courses").resolve(),
        )
        self.assertEqual(
            config.upload_dir,
            (self.project_root / "data" / "uploads").resolve(),
        )

    def test_absolute_environment_paths_are_used(self) -> None:
        configured_root = Path(self.tmp.name) / "staging"
        environment = {
            "INTERTOP_DB_PATH": str(configured_root / "training.db"),
            "INTERTOP_COURSES_DIR": str(configured_root / "courses"),
            "INTERTOP_UPLOAD_DIR": str(configured_root / "uploads"),
        }

        with patch.dict(os.environ, environment, clear=True):
            config = RuntimePathsConfig.from_environment(
                project_root=self.project_root,
            )

        self.assertEqual(config.db_path, (configured_root / "training.db").resolve())
        self.assertEqual(config.courses_dir, (configured_root / "courses").resolve())
        self.assertEqual(config.upload_dir, (configured_root / "uploads").resolve())

    def test_relative_paths_are_resolved_from_project_root(self) -> None:
        with patch.dict(
            os.environ,
            {
                "INTERTOP_DB_PATH": "state/staging.db",
                "INTERTOP_COURSES_DIR": "content/staging",
                "INTERTOP_UPLOAD_DIR": "state/uploads",
            },
            clear=True,
        ):
            config = RuntimePathsConfig.from_environment(
                project_root=self.project_root,
            )

        self.assertEqual(
            config.db_path,
            (self.project_root / "state" / "staging.db").resolve(),
        )
        self.assertEqual(
            config.courses_dir,
            (self.project_root / "content" / "staging").resolve(),
        )
        self.assertEqual(
            config.upload_dir,
            (self.project_root / "state" / "uploads").resolve(),
        )

    def test_blank_configured_path_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"INTERTOP_DB_PATH": "   "},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "INTERTOP_DB_PATH"):
                RuntimePathsConfig.from_environment(
                    project_root=self.project_root,
                )


if __name__ == "__main__":
    unittest.main()
