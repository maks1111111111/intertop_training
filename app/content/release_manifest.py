"""Release manifest for the Content Engine.

Builds an in-memory summary of a published course release, including
snapshot location and file-level change counts from a :class:`SnapshotDiff`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.content.diff import SnapshotDiff


@dataclass(frozen=True)
class ReleaseManifest:
    """Summary of a published course release.

    Counts reflect file-level differences between snapshots. The manifest
    is an in-memory object; no files are written by this module.
    """

    version: int
    published: str
    snapshot: str
    added_files: int
    removed_files: int
    changed_files: int
    unchanged_files: int


def _validate_version(version: int) -> None:
    """Ensure ``version`` is a positive integer (bool is not accepted)."""
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"Version must be a positive integer, got {version!r}")
    if version < 1:
        raise ValueError(f"Version must be at least 1, got {version}")


def _validate_published(published: str) -> None:
    """Ensure ``published`` is a non-empty string."""
    if not isinstance(published, str):
        raise ValueError(
            f"Published timestamp must be a string, got {type(published).__name__}"
        )
    if not published.strip():
        raise ValueError("Published timestamp must not be empty")


def build_release_manifest(
    *,
    version: int,
    published: str,
    snapshot: Path,
    diff: SnapshotDiff,
) -> ReleaseManifest:
    """Build an in-memory release manifest from snapshot metadata and a diff.

    Args:
        version: Published course version. Must be a positive integer; bool
            is not accepted.
        published: Publication timestamp (for example an ISO 8601 UTC string).
            Must be a non-empty string after stripping whitespace.
        snapshot: Path to the course snapshot directory. Stored as a POSIX
            path string in the manifest.
        diff: File-level differences used to compute change counts.

    Returns:
        A :class:`ReleaseManifest` describing the release.

    Raises:
        ValueError: If ``version`` or ``published`` is invalid.
    """
    _validate_version(version)
    _validate_published(published)

    return ReleaseManifest(
        version=version,
        published=published,
        snapshot=snapshot.as_posix(),
        added_files=len(diff.added_files),
        removed_files=len(diff.removed_files),
        changed_files=len(diff.changed_files),
        unchanged_files=len(diff.unchanged_files),
    )
