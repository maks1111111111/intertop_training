"""Project environment bootstrap.

Loads variables from ``.env`` once per process at application entry points.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_env_loaded = False


def load_project_env() -> None:
    """Load ``.env`` from the project root if not already loaded."""
    global _env_loaded
    if _env_loaded:
        return
    load_dotenv(_PROJECT_ROOT / ".env")
    _env_loaded = True
