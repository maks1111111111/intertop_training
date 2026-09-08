"""Verified, rollback-safe SQLite restore for offline operations."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from app.database.backup import (
    DEFAULT_BACKUPS_TO_KEEP,
    DatabaseBackupError,
    create_database_backup,
)


class DatabaseRestoreError(RuntimeError):
    """Raised when a database cannot be safely restored."""


@dataclass(frozen=True)
class DatabaseRestoreResult:
    """Paths affected by one successful restore operation."""

    database_path: Path
    safety_backup_path: Path | None


def restore_database_backup(
    backup_path: Path,
    db_path: Path,
    safety_backup_dir: Path,
    *,
    keep_safety_backups: int = DEFAULT_BACKUPS_TO_KEEP,
) -> DatabaseRestoreResult:
    """Atomically restore a verified backup after preserving current data."""
    source_path = Path(backup_path).resolve()
    destination_path = Path(db_path).resolve()
    safety_dir = Path(safety_backup_dir).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == destination_path:
        raise DatabaseRestoreError("backup and database paths must differ")
    if destination_path.exists() and not destination_path.is_file():
        raise DatabaseRestoreError("database path is not a regular file")

    _verify_database(source_path)
    _checkpoint_database_for_restore(destination_path)

    safety_backup_path = None
    if destination_path.exists():
        safety_backup_path = create_database_backup(
            destination_path,
            safety_dir,
            keep_last=keep_safety_backups,
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.parent / (
        f".{destination_path.name}.{uuid4().hex}.restore.tmp"
    )
    try:
        shutil.copyfile(source_path, temporary_path)
        temporary_path.chmod(0o600)
        _verify_database(temporary_path)
        _replace_database_file(temporary_path, destination_path)
        _fsync_directory(destination_path.parent)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return DatabaseRestoreResult(
        database_path=destination_path,
        safety_backup_path=safety_backup_path,
    )


def _verify_database(db_path: Path) -> None:
    uri = f"{db_path.as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            integrity_result = connection.execute("PRAGMA quick_check").fetchone()
            users_table = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'users'
                """
            ).fetchone()
    except sqlite3.Error as error:
        raise DatabaseRestoreError("SQLite backup verification failed") from error

    if integrity_result is None or integrity_result[0] != "ok":
        raise DatabaseRestoreError("SQLite backup integrity check failed")
    if users_table is None:
        raise DatabaseRestoreError("SQLite backup is missing the users table")


def _checkpoint_database_for_restore(db_path: Path) -> None:
    if not db_path.exists():
        return

    connection = None
    try:
        connection = sqlite3.connect(db_path, timeout=0)
        connection.execute("PRAGMA busy_timeout = 0")
        checkpoint = connection.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
    except sqlite3.Error as error:
        raise DatabaseRestoreError(
            "database is busy; stop the application before restore"
        ) from error
    finally:
        if connection is not None:
            connection.close()

    if checkpoint is None or checkpoint[0] != 0:
        raise DatabaseRestoreError(
            "database is busy; stop the application before restore"
        )


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_database_file(source_path: Path, destination_path: Path) -> None:
    os.replace(source_path, destination_path)


def main(argv: Sequence[str] | None = None) -> int:
    """Restore one verified backup from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--safety-backup-dir", required=True, type=Path)
    parser.add_argument(
        "--keep-safety-backups",
        type=int,
        default=DEFAULT_BACKUPS_TO_KEEP,
    )
    args = parser.parse_args(argv)

    try:
        result = restore_database_backup(
            args.backup,
            args.db,
            args.safety_backup_dir,
            keep_safety_backups=args.keep_safety_backups,
        )
    except (
        DatabaseBackupError,
        DatabaseRestoreError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        parser.exit(1, f"restore failed: {error}\n")

    print(result.database_path)
    if result.safety_backup_path is not None:
        print(f"safety backup: {result.safety_backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
