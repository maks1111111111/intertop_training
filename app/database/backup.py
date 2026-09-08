"""Consistent, verified SQLite backups for production operations."""

from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4


DEFAULT_BACKUPS_TO_KEEP = 14


class DatabaseBackupError(RuntimeError):
    """Raised when a database backup cannot be safely created."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_database_backup(
    db_path: Path,
    backup_dir: Path,
    *,
    keep_last: int = DEFAULT_BACKUPS_TO_KEEP,
    clock: Callable[[], datetime] = _utc_now,
) -> Path:
    """Create an atomic, integrity-checked snapshot of a live SQLite database."""
    source_path = Path(db_path).resolve()
    destination_dir = Path(backup_dir).resolve()
    _validate_keep_last(keep_last)

    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _format_timestamp(clock())
    filename_prefix = f"{source_path.stem}-backup-"
    backup_path = _available_backup_path(
        destination_dir,
        f"{filename_prefix}{timestamp}",
    )
    temporary_path = destination_dir / f".{backup_path.name}.{uuid4().hex}.tmp"

    try:
        _copy_and_verify_database(source_path, temporary_path)
        temporary_path.chmod(0o600)
        os.replace(temporary_path, backup_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    _prune_old_backups(
        destination_dir,
        filename_prefix=filename_prefix,
        keep_last=keep_last,
    )
    return backup_path


def _copy_and_verify_database(source_path: Path, destination_path: Path) -> None:
    source_uri = f"{source_path.as_uri()}?mode=ro"
    try:
        with closing(
            sqlite3.connect(source_uri, uri=True)
        ) as source_connection:
            with closing(
                sqlite3.connect(destination_path)
            ) as destination_connection:
                source_connection.backup(destination_connection)
                integrity_result = destination_connection.execute(
                    "PRAGMA quick_check"
                ).fetchone()
    except sqlite3.Error as error:
        raise DatabaseBackupError("SQLite backup failed") from error

    if integrity_result is None or integrity_result[0] != "ok":
        raise DatabaseBackupError("SQLite backup integrity check failed")


def _format_timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("backup clock must return a timezone-aware datetime")
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _available_backup_path(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.sqlite3"
    suffix = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{suffix}.sqlite3"
        suffix += 1
    return candidate


def _validate_keep_last(keep_last: int) -> None:
    if isinstance(keep_last, bool) or not isinstance(keep_last, int):
        raise TypeError("keep_last must be an integer")
    if keep_last < 1:
        raise ValueError("keep_last must be at least 1")


def _prune_old_backups(
    backup_dir: Path,
    *,
    filename_prefix: str,
    keep_last: int,
) -> None:
    backups = sorted(
        path
        for path in backup_dir.glob(f"{filename_prefix}*.sqlite3")
        if path.is_file()
    )
    for expired_backup in backups[:-keep_last]:
        expired_backup.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    """Create one verified backup from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--keep-last",
        type=int,
        default=DEFAULT_BACKUPS_TO_KEEP,
    )
    args = parser.parse_args(argv)

    try:
        backup_path = create_database_backup(
            args.db,
            args.output_dir,
            keep_last=args.keep_last,
        )
    except (DatabaseBackupError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"backup failed: {error}\n")

    print(backup_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
