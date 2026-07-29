"""Course snapshot storage for the Content Engine.

Creates immutable copies of published course content under
``course_dir / .snapshots / vNNNN``.
"""

import shutil
import tempfile
from pathlib import Path

SNAPSHOTS_DIR_NAME = ".snapshots"


def _version_dir_name(version: int) -> str:
    """Return the snapshot directory name for a course version."""
    return f"v{version:04d}"


def _validate_course_dir(course_dir: Path) -> None:
    """Ensure ``course_dir`` exists and is a directory."""
    if not course_dir.exists():
        raise ValueError(f"Course directory does not exist: {course_dir}")
    if not course_dir.is_dir():
        raise ValueError(f"Course path is not a directory: {course_dir}")


def _validate_version(version: int) -> None:
    """Ensure ``version`` is a positive integer (bool is not accepted)."""
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"Version must be a positive integer, got {version!r}")
    if version < 1:
        raise ValueError(f"Version must be at least 1, got {version}")


def _cleanup_temp_dir(temp_dir: Path) -> None:
    """Remove a temporary snapshot directory if it still exists."""
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def create_snapshot(course_dir: Path, version: int) -> Path:
    """Create or return an existing snapshot of a course directory.

    Snapshots are stored in ``course_dir / .snapshots / vNNNN``, where ``NNNN``
    is the version formatted with at least four digits (for example ``v0001``,
    ``v0015``, ``v1000``).

    The full course directory is copied into the snapshot, except for the
    ``.snapshots`` directory itself, which is never included in a snapshot.

    If a snapshot for the given version already exists, it is not modified and
    its path is returned. This operation is idempotent.

    Args:
        course_dir: Path to the course directory (for example ``courses/brands``).
        version: Published course version to snapshot.

    Returns:
        Path to the snapshot directory.

    Raises:
        ValueError: If ``course_dir`` is missing or not a directory, or if
            ``version`` is invalid.
        FileExistsError: If the snapshot path exists but is not a directory.
        OSError: If the snapshot directory cannot be created or copied.
    """
    _validate_course_dir(course_dir)
    _validate_version(version)

    snapshots_root = course_dir / SNAPSHOTS_DIR_NAME
    snapshot_dir = snapshots_root / _version_dir_name(version)

    if snapshot_dir.exists():
        if snapshot_dir.is_dir():
            return snapshot_dir
        raise FileExistsError(
            f"Snapshot path exists but is not a directory: {snapshot_dir}"
        )

    snapshots_root.mkdir(parents=True, exist_ok=True)

    course_dir_resolved = course_dir.resolve()

    def _ignore_snapshots(directory: str, names: list[str]) -> list[str]:
        if Path(directory).resolve() == course_dir_resolved:
            return [SNAPSHOTS_DIR_NAME]
        return []

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{snapshot_dir.name}.",
            dir=str(snapshots_root),
        )
    )

    try:
        shutil.copytree(
            course_dir,
            temp_dir,
            ignore=_ignore_snapshots,
            dirs_exist_ok=True,
        )
    except OSError:
        _cleanup_temp_dir(temp_dir)
        raise

    try:
        temp_dir.rename(snapshot_dir)
    except OSError:
        _cleanup_temp_dir(temp_dir)
        if snapshot_dir.exists():
            if snapshot_dir.is_dir():
                return snapshot_dir
            raise FileExistsError(
                f"Snapshot path exists but is not a directory: {snapshot_dir}"
            )
        raise

    return snapshot_dir
