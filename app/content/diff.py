"""Snapshot comparison for the Content Engine.

Compares two course snapshot directories and reports file-level
differences without interpreting course content.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_CONTENT_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class SnapshotDiff:
    """File-level differences between two course snapshots.

    All paths are relative to the snapshot root. Only regular files are
    compared; directories are not listed separately.
    """

    added_files: list[Path]
    removed_files: list[Path]
    changed_files: list[Path]
    unchanged_files: list[Path]


def _validate_snapshot_dir(snapshot: Path) -> None:
    """Ensure ``snapshot`` exists and is a directory."""
    if not snapshot.exists():
        raise ValueError(f"Snapshot directory does not exist: {snapshot}")
    if not snapshot.is_dir():
        raise ValueError(f"Snapshot path is not a directory: {snapshot}")


def _collect_regular_files(snapshot: Path) -> dict[Path, Path]:
    """Map relative paths to absolute file paths under ``snapshot``."""
    files: dict[Path, Path] = {}
    for path in snapshot.rglob("*"):
        if path.is_file():
            files[path.relative_to(snapshot)] = path
    return files


def _files_have_same_content(left: Path, right: Path) -> bool:
    """Return whether two files have identical byte content.

    File content is compared in fixed-size blocks without loading entire
    files into memory.
    """
    if left.stat().st_size != right.stat().st_size:
        return False

    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            left_chunk = left_file.read(_CONTENT_CHUNK_SIZE)
            right_chunk = right_file.read(_CONTENT_CHUNK_SIZE)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def compare_snapshots(old_snapshot: Path, new_snapshot: Path) -> SnapshotDiff:
    """Compare two snapshot directories and return file-level differences.

    Both snapshots are walked recursively. Only regular files are included
    in the result; directory entries are ignored. File content is compared
    byte-by-byte, not by modification time.

    All returned paths are relative to the corresponding snapshot root and
    sorted lexicographically within each category.

    Args:
        old_snapshot: Path to the earlier snapshot directory.
        new_snapshot: Path to the later snapshot directory.

    Returns:
        A :class:`SnapshotDiff` describing added, removed, changed, and
        unchanged files.

    Raises:
        ValueError: If either path does not exist or is not a directory.
    """
    _validate_snapshot_dir(old_snapshot)
    _validate_snapshot_dir(new_snapshot)

    old_files = _collect_regular_files(old_snapshot)
    new_files = _collect_regular_files(new_snapshot)

    old_paths = set(old_files)
    new_paths = set(new_files)

    added_files = sorted(new_paths - old_paths)
    removed_files = sorted(old_paths - new_paths)

    changed_files: list[Path] = []
    unchanged_files: list[Path] = []
    for relative_path in sorted(old_paths & new_paths):
        if _files_have_same_content(old_files[relative_path], new_files[relative_path]):
            unchanged_files.append(relative_path)
        else:
            changed_files.append(relative_path)

    return SnapshotDiff(
        added_files=added_files,
        removed_files=removed_files,
        changed_files=changed_files,
        unchanged_files=unchanged_files,
    )
