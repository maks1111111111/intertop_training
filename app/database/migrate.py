"""Apply idempotent database migrations before the read-only deployment audit."""

from __future__ import annotations

import sys

from app.database.db import initialize_database
from app.deployment_config import DeploymentConfig
from app.env import load_project_env
from app.runtime_paths_config import RuntimePathsConfig


def run() -> int:
    """Validate runtime paths and bring the configured database schema current."""
    load_project_env()
    try:
        deployment = DeploymentConfig.from_environment()
        runtime_paths = RuntimePathsConfig.from_environment()
        deployment.validate_runtime_paths(runtime_paths)
        initialize_database(runtime_paths.db_path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: database migration failed: {error}", file=sys.stderr)
        return 1
    print("DATABASE_MIGRATION\nstatus=complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
