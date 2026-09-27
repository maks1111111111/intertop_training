"""Verify the latest encrypted offsite backup without touching production data."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, Sequence

from app.database.offsite_backup import (
    OffsiteBackupError,
    _create_s3_client,
    _decode_encryption_key,
    _required_env,
    decrypt_archive,
)


_BACKUP_PREFIX = "daily/"
_BACKUP_SUFFIX = ".tar.gz.aes256gcm"
_MANIFEST_NAME = "manifest.json"
_DATABASE_NAME = "database/training.db"
_REQUIRED_MANIFEST = {
    "format": "mentorconnect-offsite-v1",
    "database": _DATABASE_NAME,
    "courses": "courses",
    "uploads": "uploads",
}


class OffsiteRestoreVerificationError(RuntimeError):
    """Raised when a recovery drill cannot validate an offsite backup."""


class RestoreVerificationS3Client(Protocol):
    """The small read-only S3 surface needed by a restore drill."""

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]: ...

    def download_file(self, bucket: str, key: str, filename: str) -> None: ...


@dataclass(frozen=True)
class OffsiteRestoreVerificationResult:
    """Non-sensitive evidence produced by a successful restore drill."""

    object_key: str
    database_verified: bool
    course_entries: int
    upload_entries: int


def verify_latest_offsite_backup(
    *,
    client: RestoreVerificationS3Client,
    bucket: str,
    encryption_key: bytes,
    work_dir: Path,
) -> OffsiteRestoreVerificationResult:
    """Download, decrypt, and validate the newest backup in an isolated temp dir."""
    normalized_bucket = str(bucket or "").strip()
    if not normalized_bucket:
        raise OffsiteRestoreVerificationError("backup bucket is required")

    object_key = _latest_backup_key(client, normalized_bucket)
    root = _prepare_work_dir(work_dir)
    with tempfile.TemporaryDirectory(
        prefix="mentorconnect-restore-drill-",
        dir=root,
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        encrypted_path = temporary_root / "backup.tar.gz.aes256gcm"
        plaintext_path = temporary_root / "backup.tar.gz"
        database_path = temporary_root / "training.db"

        client.download_file(normalized_bucket, object_key, str(encrypted_path))
        if not encrypted_path.is_file():
            raise OffsiteRestoreVerificationError("backup download did not create a file")
        encrypted_path.chmod(0o600)
        decrypt_archive(encrypted_path, plaintext_path, encryption_key)
        course_entries, upload_entries = _validate_archive(
            plaintext_path,
            database_path,
        )
        _verify_database(database_path)

    return OffsiteRestoreVerificationResult(
        object_key=object_key,
        database_verified=True,
        course_entries=course_entries,
        upload_entries=upload_entries,
    )


def _latest_backup_key(
    client: RestoreVerificationS3Client,
    bucket: str,
) -> str:
    request: dict[str, object] = {"Bucket": bucket, "Prefix": _BACKUP_PREFIX}
    newest: tuple[datetime, str] | None = None

    while True:
        response = client.list_objects_v2(**request)
        contents = response.get("Contents", [])
        if not isinstance(contents, list):
            raise OffsiteRestoreVerificationError("S3 returned an invalid object listing")
        for item in contents:
            if not isinstance(item, dict):
                continue
            key = item.get("Key")
            modified = item.get("LastModified")
            if (
                not isinstance(key, str)
                or not key.startswith(_BACKUP_PREFIX)
                or not key.endswith(_BACKUP_SUFFIX)
                or not isinstance(modified, datetime)
            ):
                continue
            candidate = (modified, key)
            if newest is None or candidate > newest:
                newest = candidate

        if response.get("IsTruncated") is not True:
            break
        continuation = response.get("NextContinuationToken")
        if not isinstance(continuation, str) or not continuation:
            raise OffsiteRestoreVerificationError("S3 omitted object-list pagination")
        request["ContinuationToken"] = continuation

    if newest is None:
        raise OffsiteRestoreVerificationError("no encrypted offsite backups found")
    return newest[1]


def _prepare_work_dir(work_dir: Path) -> Path:
    resolved = Path(work_dir).resolve()
    if resolved.exists() and not resolved.is_dir():
        raise OffsiteRestoreVerificationError("restore work path is not a directory")
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved.chmod(0o700)
    return resolved


def _validate_archive(
    archive_path: Path,
    database_path: Path,
) -> tuple[int, int]:
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            _validate_member_names(members)
            manifest = _read_manifest(archive)
            _validate_manifest(manifest)
            database_member = _database_member(members)
            _extract_database(archive, database_member, database_path)
            names = tuple(member.name.rstrip("/") for member in members)
    except (OSError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OffsiteRestoreVerificationError("backup archive validation failed") from error

    course_entries = _entry_count(names, "courses")
    upload_entries = _entry_count(names, "uploads")
    if course_entries == 0 or upload_entries == 0:
        raise OffsiteRestoreVerificationError("backup archive is missing required data roots")
    return course_entries, upload_entries


def _validate_member_names(members: Sequence[tarfile.TarInfo]) -> None:
    for member in members:
        path = PurePosixPath(member.name)
        if (
            not member.name
            or path.is_absolute()
            or any(part in ("", ".", "..") for part in path.parts)
        ):
            raise OffsiteRestoreVerificationError("backup archive contains an unsafe path")


def _read_manifest(archive: tarfile.TarFile) -> dict[str, object]:
    try:
        member = archive.getmember(_MANIFEST_NAME)
    except KeyError as error:
        raise OffsiteRestoreVerificationError("backup archive is missing its manifest") from error
    source = archive.extractfile(member)
    if source is None:
        raise OffsiteRestoreVerificationError("backup archive manifest is unreadable")
    with source:
        payload = json.loads(source.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise OffsiteRestoreVerificationError("backup archive manifest is invalid")
    return payload


def _validate_manifest(manifest: dict[str, object]) -> None:
    for key, value in _REQUIRED_MANIFEST.items():
        if manifest.get(key) != value:
            raise OffsiteRestoreVerificationError("backup archive manifest is invalid")


def _database_member(members: Sequence[tarfile.TarInfo]) -> tarfile.TarInfo:
    for member in members:
        if member.name == _DATABASE_NAME and member.isfile():
            return member
    raise OffsiteRestoreVerificationError("backup archive is missing its database")


def _extract_database(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    destination: Path,
) -> None:
    source = archive.extractfile(member)
    if source is None:
        raise OffsiteRestoreVerificationError("backup database is unreadable")
    with source, destination.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        shutil.copyfileobj(source, output)


def _entry_count(names: Sequence[str], root: str) -> int:
    return sum(name == root or name.startswith(f"{root}/") for name in names)


def _verify_database(db_path: Path) -> None:
    uri = f"{db_path.as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            users_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone()
    except sqlite3.Error as error:
        raise OffsiteRestoreVerificationError("backup database verification failed") from error
    if quick_check is None or quick_check[0] != "ok" or users_table is None:
        raise OffsiteRestoreVerificationError("backup database verification failed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        endpoint = _required_env("INTERTOP_S3_ENDPOINT")
        region = _required_env("INTERTOP_S3_REGION")
        bucket = _required_env("INTERTOP_S3_BUCKET")
        access_key = _required_env("INTERTOP_S3_ACCESS_KEY_ID")
        secret_key = _required_env("INTERTOP_S3_SECRET_ACCESS_KEY")
        encryption_key = _decode_encryption_key(
            _required_env("INTERTOP_BACKUP_ENCRYPTION_KEY")
        )
        client = _create_s3_client(
            endpoint=endpoint,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
        )
        result = verify_latest_offsite_backup(
            client=client,
            bucket=bucket,
            encryption_key=encryption_key,
            work_dir=args.work_dir,
        )
    except (OffsiteBackupError, OffsiteRestoreVerificationError, OSError, ValueError) as error:
        parser.exit(1, f"offsite restore verification failed: {error}\n")

    print(f"s3://{bucket}/{result.object_key}")
    print("database=verified")
    print(f"course_entries={result.course_entries}")
    print(f"upload_entries={result.upload_entries}")
    print("status=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
