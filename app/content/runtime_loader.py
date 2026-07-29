"""Runtime loader for published Content Engine content packs.

Loads a validated :class:`ContentPack` into an immutable runtime view without
rescanning the filesystem or recomputing checksums.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.content.content_pack import ContentPack


@dataclass(frozen=True)
class RuntimeContent:
    """Immutable runtime view of a published course content pack.

    The loader trusts a previously built :class:`ContentPack` after validating
    its internal consistency and snapshot availability. It does not rescan the
    snapshot directory or recompute checksums.
    """

    course_slug: str
    version: int
    snapshot: str
    files: tuple[str, ...]
    checksum_sha256: str


def _validate_version(version: int) -> None:
    """Ensure ``version`` is a positive integer (bool is not accepted)."""
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"Version must be a positive integer, got {version!r}")
    if version < 1:
        raise ValueError(f"Version must be at least 1, got {version}")


def _validate_files_count(files_count: int, files: tuple[str, ...]) -> None:
    """Ensure ``files_count`` matches the number of listed files."""
    if files_count != len(files):
        raise ValueError(
            "files_count does not match len(files): "
            f"files_count={files_count}, len(files)={len(files)}"
        )


def _validate_checksum_sha256(checksum_sha256: str) -> None:
    """Ensure ``checksum_sha256`` is a non-empty string."""
    if not isinstance(checksum_sha256, str):
        raise ValueError(
            "checksum_sha256 must be a string, "
            f"got {type(checksum_sha256).__name__}"
        )
    if not checksum_sha256:
        raise ValueError("checksum_sha256 must not be empty")


def _validate_snapshot(snapshot: str) -> None:
    """Ensure ``snapshot`` points to an existing directory."""
    if not isinstance(snapshot, str):
        raise ValueError(
            f"snapshot must be a string, got {type(snapshot).__name__}"
        )
    if not snapshot:
        raise ValueError("snapshot must not be empty")

    snapshot_path = Path(snapshot)
    if not snapshot_path.exists():
        raise ValueError(f"Snapshot directory does not exist: {snapshot}")
    if not snapshot_path.is_dir():
        raise ValueError(f"Snapshot path is not a directory: {snapshot}")


def _validate_content_pack(content_pack: ContentPack) -> None:
    """Validate a :class:`ContentPack` before runtime loading."""
    _validate_version(content_pack.version)
    _validate_files_count(content_pack.files_count, content_pack.files)
    _validate_checksum_sha256(content_pack.checksum_sha256)
    _validate_snapshot(content_pack.snapshot)


def load_runtime_content(content_pack: ContentPack) -> RuntimeContent:
    """Load a validated runtime view from a :class:`ContentPack`.

    The function checks internal consistency of ``content_pack`` and verifies
    that the referenced snapshot directory exists. It does not rescan the
    snapshot, recompute checksums, or read course files such as ``lesson.json``.

    Args:
        content_pack: A previously built content pack description.

    Returns:
        An immutable :class:`RuntimeContent` ready for runtime use.

    Raises:
        ValueError: If ``content_pack`` is inconsistent or its snapshot is
            unavailable.
    """
    _validate_content_pack(content_pack)

    return RuntimeContent(
        course_slug=content_pack.course_slug,
        version=content_pack.version,
        snapshot=content_pack.snapshot,
        files=content_pack.files,
        checksum_sha256=content_pack.checksum_sha256,
    )
