"""Environment-configurable runtime paths shared by Web and Telegram."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DB_PATH_ENV = "INTERTOP_DB_PATH"
COURSES_DIR_ENV = "INTERTOP_COURSES_DIR"
UPLOAD_DIR_ENV = "INTERTOP_UPLOAD_DIR"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class RuntimePathsConfig:
    """Persistent paths used by all application entry points."""

    db_path: Path
    courses_dir: Path
    upload_dir: Path

    @classmethod
    def from_environment(
        cls,
        *,
        project_root: Path = _PROJECT_ROOT,
    ) -> "RuntimePathsConfig":
        """Load isolated runtime paths while preserving local defaults."""
        root = Path(project_root).resolve()
        return cls(
            db_path=_read_path(DB_PATH_ENV, root / "data" / "training.db", root),
            courses_dir=_read_path(COURSES_DIR_ENV, root / "courses", root),
            upload_dir=_read_path(UPLOAD_DIR_ENV, root / "data" / "uploads", root),
        )


def _read_path(name: str, default: Path, project_root: Path) -> Path:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default.resolve()

    normalized = raw_value.strip()
    if not normalized:
        raise RuntimeError(f"{name} environment variable must not be empty.")

    configured_path = Path(normalized).expanduser()
    if not configured_path.is_absolute():
        configured_path = project_root / configured_path
    return configured_path.resolve()
