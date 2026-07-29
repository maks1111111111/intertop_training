"""Publication history for the Content Engine.

Records publication attempts in a per-course ``.publish-history.json`` file.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PUBLISH_HISTORY_FILENAME = ".publish-history.json"


def _utc_timestamp() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_history(history_path: Path) -> List[Dict[str, Any]]:
    """Load existing publication history entries, or return an empty list.

    Returns an empty list when the history file does not exist.

    Raises:
        ValueError: If the file exists but cannot be read, contains invalid JSON,
            has a non-list root value, or contains non-object entries.
    """
    if not history_path.exists():
        return []

    try:
        raw_text = history_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except OSError as exc:
        raise ValueError(
            f"Cannot read publication history from {history_path.name}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in publication history file {history_path.name}: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            f"Publication history file {history_path.name} must contain a JSON array"
        )

    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Publication history entry at index {index} must be a JSON object"
            )

    return data


def record_publication(
    course_dir: Path,
    published: bool,
    gate: dict,
) -> None:
    """Append a publication attempt to the course publication history.

    History is stored in ``course_dir / .publish-history.json`` as a JSON array.
    Each entry contains ``timestamp``, ``published``, ``errors``, and
    ``warnings``.

    Args:
        course_dir: Path to the course directory (for example ``courses/brands``).
        published: Whether the course was published.
        gate: Release gate dictionary from
            :meth:`~app.content.models.ValidationReport.release_gate`.

    Raises:
        ValueError: If an existing history file is corrupted or invalid.
        OSError: If the history file cannot be written.
    """
    history_path = course_dir / PUBLISH_HISTORY_FILENAME
    history = _load_history(history_path)

    entry = {
        "timestamp": _utc_timestamp(),
        "published": published,
        "errors": gate.get("errors", 0),
        "warnings": gate.get("warnings", 0),
    }
    history.append(entry)

    history_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
