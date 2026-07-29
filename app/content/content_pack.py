"""Content pack builder for the Content Engine.

Builds a deterministic description of a published course snapshot, including
file inventory, total size, and a content-addressable checksum.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

RELEASE_MANIFEST_FILENAME = "release-manifest.json"

_CONTENT_CHUNK_SIZE = 64 * 1024
_LENGTH_PREFIX_SIZE = 8


@dataclass(frozen=True)
class ContentPack:
    """Deterministic description of a course snapshot content pack.

    All file paths in :attr:`files` are relative POSIX paths within the
    snapshot. The checksum depends on path order, relative paths, and file
    contents only — not on absolute paths or filesystem metadata.
    """

    course_slug: str
    version: int
    snapshot: str
    files: tuple[str, ...]
    files_count: int
    total_size_bytes: int
    checksum_sha256: str


def _validate_version(version: int) -> None:
    """Ensure ``version`` is a positive integer (bool is not accepted)."""
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"Version must be a positive integer, got {version!r}")
    if version < 1:
        raise ValueError(f"Version must be at least 1, got {version}")


def _validate_course_dir(course_dir: Path) -> str:
    """Ensure ``course_dir`` exists, is a directory, and has a non-empty name."""
    if not course_dir.exists():
        raise FileNotFoundError(f"Course directory does not exist: {course_dir}")
    if not course_dir.is_dir():
        raise NotADirectoryError(f"Course path is not a directory: {course_dir}")

    course_slug = course_dir.name
    if not course_slug:
        raise ValueError("Course directory name must not be empty")

    return course_slug


def _validate_snapshot_dir(snapshot_dir: Path) -> None:
    """Ensure ``snapshot_dir`` exists and is a directory."""
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Snapshot directory does not exist: {snapshot_dir}")
    if not snapshot_dir.is_dir():
        raise NotADirectoryError(f"Snapshot path is not a directory: {snapshot_dir}")


def _relative_posix_path(path: Path, root: Path) -> str:
    """Return the relative POSIX path of ``path`` under ``root``."""
    return path.relative_to(root).as_posix()


def _should_include_file(relative_path: str) -> bool:
    """Return whether a snapshot file belongs in the content pack."""
    return relative_path != RELEASE_MANIFEST_FILENAME


def _collect_pack_files(snapshot_dir: Path) -> tuple[tuple[str, Path], ...]:
    """Collect regular, non-symlink files included in the content pack."""
    collected: list[tuple[str, Path]] = []

    for path in snapshot_dir.rglob("*"):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue

        relative_path = _relative_posix_path(path, snapshot_dir)
        if not _should_include_file(relative_path):
            continue

        collected.append((relative_path, path))

    collected.sort(key=lambda item: item[0])
    return tuple(collected)


def _compute_total_size_bytes(files: tuple[tuple[str, Path], ...]) -> int:
    """Return the combined size of all included files in bytes."""
    return sum(file_path.stat().st_size for _, file_path in files)


def _encode_length(value: int) -> bytes:
    """Encode a non-negative integer as a fixed 8-byte big-endian prefix."""
    return value.to_bytes(_LENGTH_PREFIX_SIZE, byteorder="big", signed=False)


def _update_checksum_for_file(
    digest,
    relative_path: str,
    file_path: Path,
) -> None:
    """Update ``digest`` with one file's length-prefixed path and content."""
    path_bytes = relative_path.encode("utf-8")
    digest.update(_encode_length(len(path_bytes)))
    digest.update(path_bytes)

    file_size = file_path.stat().st_size
    digest.update(_encode_length(file_size))

    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(_CONTENT_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)


def _compute_checksum_sha256(files: tuple[tuple[str, Path], ...]) -> str:
    """Return a deterministic SHA-256 checksum for the content pack."""
    digest = hashlib.sha256()
    for relative_path, file_path in files:
        _update_checksum_for_file(digest, relative_path, file_path)
    return digest.hexdigest()


def build_content_pack(
    course_dir: Path,
    snapshot_dir: Path,
    version: int,
) -> ContentPack:
    """Build a deterministic content pack description from a course snapshot.

    The pack includes all regular files under ``snapshot_dir``, except for
    ``release-manifest.json``, which is release metadata and not part of the
    distributable course content.

    File paths are stored as relative POSIX paths sorted lexicographically.
    The checksum depends on path order, relative paths, and file contents only.

    Args:
        course_dir: Path to the course directory (for example ``courses/brands``).
        snapshot_dir: Path to the snapshot directory to describe.
        version: Published course version for the snapshot.

    Returns:
        A :class:`ContentPack` describing the snapshot content.

    Raises:
        FileNotFoundError: If ``course_dir`` or ``snapshot_dir`` does not exist.
        NotADirectoryError: If ``course_dir`` or ``snapshot_dir`` is not a
            directory.
        ValueError: If ``version`` is invalid or ``course_dir`` has an empty
            name.
        OSError: If file metadata or content cannot be read.
    """
    course_slug = _validate_course_dir(course_dir)
    _validate_snapshot_dir(snapshot_dir)
    _validate_version(version)

    collected_files = _collect_pack_files(snapshot_dir)
    relative_paths = tuple(relative_path for relative_path, _ in collected_files)
    total_size_bytes = _compute_total_size_bytes(collected_files)
    checksum_sha256 = _compute_checksum_sha256(collected_files)

    return ContentPack(
        course_slug=course_slug,
        version=version,
        snapshot=snapshot_dir.as_posix(),
        files=relative_paths,
        files_count=len(relative_paths),
        total_size_bytes=total_size_bytes,
        checksum_sha256=checksum_sha256,
    )
