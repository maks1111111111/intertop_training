"""Freshness checks for successful production automation runs."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable


AUTOMATION_HEALTH_DIR_ENV = "INTERTOP_AUTOMATION_HEALTH_DIR"
AUTOMATION_HEALTH_MAX_AGE_SECONDS_ENV = (
    "INTERTOP_AUTOMATION_HEALTH_MAX_AGE_SECONDS"
)
DEFAULT_AUTOMATION_HEALTH_DIR = Path("/srv/intertop-training/monitoring")
DEFAULT_MAX_AGE_SECONDS = 27 * 60 * 60
REQUIRED_SUCCESS_MARKERS = (
    "audit-success",
    "offsite-backup-success",
)


def automation_is_healthy(
    *,
    now: float | None = None,
    health_dir: Path | None = None,
    max_age_seconds: int | None = None,
    required_markers: Iterable[str] = REQUIRED_SUCCESS_MARKERS,
) -> bool:
    """Return whether every required success marker exists and is fresh."""
    resolved_now = time.time() if now is None else float(now)
    resolved_dir = health_dir or _health_dir_from_environment()
    resolved_max_age = (
        _max_age_from_environment()
        if max_age_seconds is None
        else int(max_age_seconds)
    )
    if resolved_max_age <= 0:
        return False

    for marker_name in required_markers:
        marker = resolved_dir / marker_name
        try:
            age_seconds = resolved_now - marker.stat().st_mtime
        except OSError:
            return False
        if age_seconds < 0 or age_seconds > resolved_max_age:
            return False
    return True


def _health_dir_from_environment() -> Path:
    raw = os.getenv(AUTOMATION_HEALTH_DIR_ENV, "").strip()
    return Path(raw) if raw else DEFAULT_AUTOMATION_HEALTH_DIR


def _max_age_from_environment() -> int:
    raw = os.getenv(AUTOMATION_HEALTH_MAX_AGE_SECONDS_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_AGE_SECONDS
    try:
        return int(raw)
    except ValueError:
        return 0
