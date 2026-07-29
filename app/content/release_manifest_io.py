"""Release manifest I/O for the Content Engine.

Persists :class:`~app.content.release_manifest.ReleaseManifest` objects as
JSON with atomic writes and strict validation on load.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.content.release_manifest import ReleaseManifest

_REQUIRED_FIELDS = frozenset(
    {
        "version",
        "published",
        "snapshot",
        "added_files",
        "removed_files",
        "changed_files",
        "unchanged_files",
    }
)


def _manifest_to_dict(manifest: ReleaseManifest) -> dict[str, object]:
    """Convert a release manifest to a JSON-serializable dictionary."""
    return {
        "version": manifest.version,
        "published": manifest.published,
        "snapshot": manifest.snapshot,
        "added_files": manifest.added_files,
        "removed_files": manifest.removed_files,
        "changed_files": manifest.changed_files,
        "unchanged_files": manifest.unchanged_files,
    }


def _validate_int_field(field_name: str, value: object) -> int:
    """Ensure ``value`` is an integer field value (bool is not accepted)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"Field '{field_name}' must be an integer, got {type(value).__name__}"
        )
    return value


def _validate_non_empty_string_field(field_name: str, value: object) -> str:
    """Ensure ``value`` is a non-empty string after stripping whitespace."""
    if not isinstance(value, str):
        raise ValueError(
            f"Field '{field_name}' must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise ValueError(f"Field '{field_name}' must not be empty")
    return value


def _validate_non_negative_int_field(field_name: str, value: object) -> int:
    """Ensure ``value`` is a non-negative integer (bool is not accepted)."""
    result = _validate_int_field(field_name, value)
    if result < 0:
        raise ValueError(
            f"Field '{field_name}' must be at least 0, got {result}"
        )
    return result


def _parse_manifest_data(data: object, *, path: Path) -> ReleaseManifest:
    """Parse and validate JSON data into a :class:`ReleaseManifest`."""
    if not isinstance(data, dict):
        raise ValueError(
            f"Release manifest must be a JSON object: {path.name}"
        )

    extra_fields = set(data.keys()) - _REQUIRED_FIELDS
    if extra_fields:
        sorted_extra = ", ".join(sorted(extra_fields))
        raise ValueError(
            f"Release manifest contains unexpected fields: {sorted_extra}"
        )

    missing_fields = _REQUIRED_FIELDS - set(data.keys())
    if missing_fields:
        sorted_missing = ", ".join(sorted(missing_fields))
        raise ValueError(
            f"Release manifest is missing required fields: {sorted_missing}"
        )

    version = _validate_int_field("version", data["version"])
    if version < 1:
        raise ValueError(f"Field 'version' must be at least 1, got {version}")

    published = _validate_non_empty_string_field("published", data["published"])
    snapshot = _validate_non_empty_string_field("snapshot", data["snapshot"])

    added_files = _validate_non_negative_int_field(
        "added_files", data["added_files"]
    )
    removed_files = _validate_non_negative_int_field(
        "removed_files", data["removed_files"]
    )
    changed_files = _validate_non_negative_int_field(
        "changed_files", data["changed_files"]
    )
    unchanged_files = _validate_non_negative_int_field(
        "unchanged_files", data["unchanged_files"]
    )

    return ReleaseManifest(
        version=version,
        published=published,
        snapshot=snapshot,
        added_files=added_files,
        removed_files=removed_files,
        changed_files=changed_files,
        unchanged_files=unchanged_files,
    )


def save_release_manifest(manifest: ReleaseManifest, path: Path) -> None:
    """Save a release manifest to a JSON file atomically.

    The manifest is written as UTF-8 JSON with ``indent=2`` and
    ``ensure_ascii=False``. A temporary file in the same directory is written
    first and then renamed to ``path``.

    Args:
        manifest: Release manifest to persist.
        path: Destination file path.

    Raises:
        OSError: If the manifest cannot be written.
    """
    payload = _manifest_to_dict(manifest)
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
        os.replace(temp_path, path)
    except OSError:
        if temp_path.exists():
            temp_path.unlink()
        raise


def load_release_manifest(path: Path) -> ReleaseManifest:
    """Load a release manifest from a JSON file.

    Args:
        path: Path to the manifest JSON file.

    Returns:
        Parsed :class:`ReleaseManifest`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file contains invalid JSON or an invalid manifest.
    """
    if not path.exists():
        raise FileNotFoundError(f"Release manifest not found: {path}")

    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in release manifest {path.name}: {exc}"
        ) from exc

    return _parse_manifest_data(data, path=path)
