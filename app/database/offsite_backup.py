"""Create a client-side encrypted application backup and upload it to S3."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Protocol, Sequence

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.database.backup import create_database_backup


ARCHIVE_MAGIC = b"MCBACKUP1\x00"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
MAX_SINGLE_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024


class OffsiteBackupError(RuntimeError):
    """Raised when an encrypted offsite backup cannot be completed safely."""


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> dict[str, object]: ...

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]: ...

    def download_file(self, bucket: str, key: str, filename: str) -> None: ...

    def list_object_versions(self, **kwargs: object) -> dict[str, object]: ...

    def delete_object(self, **kwargs: object) -> dict[str, object]: ...


class _EncryptingWriter:
    def __init__(self, output: BinaryIO, key: bytes) -> None:
        self._output = output
        self._nonce = os.urandom(NONCE_SIZE)
        self._encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(self._nonce),
        ).encryptor()
        self._output.write(ARCHIVE_MAGIC + self._nonce)
        self._closed = False

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("encrypted stream is closed")
        self._output.write(self._encryptor.update(data))
        return len(data)

    def flush(self) -> None:
        self._output.flush()

    def finish(self) -> None:
        if self._closed:
            return
        self._output.write(self._encryptor.finalize())
        self._output.write(self._encryptor.tag)
        self._output.flush()
        self._closed = True


def create_encrypted_archive(
    *,
    db_path: Path,
    courses_dir: Path,
    uploads_dir: Path,
    output_path: Path,
    encryption_key: bytes,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Path:
    """Create an encrypted tar.gz containing a verified DB and runtime files."""
    source_db = Path(db_path).resolve()
    source_courses = Path(courses_dir).resolve()
    source_uploads = Path(uploads_dir).resolve()
    destination = Path(output_path).resolve()
    _validate_sources(source_db, source_courses, source_uploads)
    _validate_encryption_key(encryption_key)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = destination.with_name(f".{destination.name}.tmp")
    temporary_output.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="mentorconnect-offsite-db-",
            dir=destination.parent,
        ) as snapshot_root:
            snapshot = create_database_backup(
                source_db,
                Path(snapshot_root),
                keep_last=1,
                clock=clock,
            )
            created_at = clock().astimezone(timezone.utc)
            manifest = {
                "format": "mentorconnect-offsite-v1",
                "created_at": created_at.isoformat(),
                "database": "database/training.db",
                "courses": "courses",
                "uploads": "uploads",
            }
            with temporary_output.open("xb") as encrypted_file:
                os.fchmod(encrypted_file.fileno(), 0o600)
                writer = _EncryptingWriter(encrypted_file, encryption_key)
                try:
                    with tarfile.open(
                        mode="w|gz",
                        fileobj=writer,
                        format=tarfile.PAX_FORMAT,
                    ) as archive:
                        _add_bytes(
                            archive,
                            "manifest.json",
                            json.dumps(manifest, sort_keys=True).encode("utf-8"),
                            created_at,
                        )
                        archive.add(snapshot, arcname="database/training.db")
                        archive.add(source_courses, arcname="courses")
                        archive.add(source_uploads, arcname="uploads")
                finally:
                    writer.finish()
        os.replace(temporary_output, destination)
        destination.chmod(0o600)
    except Exception:
        temporary_output.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    return destination


def decrypt_archive(
    encrypted_path: Path,
    output_path: Path,
    encryption_key: bytes,
) -> Path:
    """Decrypt an archive for a controlled restore test without extracting it."""
    source = Path(encrypted_path).resolve()
    destination = Path(output_path).resolve()
    _validate_encryption_key(encryption_key)
    if not source.is_file():
        raise FileNotFoundError(source)
    minimum_size = len(ARCHIVE_MAGIC) + NONCE_SIZE + TAG_SIZE
    if source.stat().st_size < minimum_size:
        raise OffsiteBackupError("encrypted archive is truncated")

    temporary_output = destination.with_name(f".{destination.name}.tmp")
    temporary_output.unlink(missing_ok=True)
    try:
        with source.open("rb") as encrypted_file:
            if encrypted_file.read(len(ARCHIVE_MAGIC)) != ARCHIVE_MAGIC:
                raise OffsiteBackupError("unsupported encrypted archive format")
            nonce = encrypted_file.read(NONCE_SIZE)
            encrypted_file.seek(-TAG_SIZE, os.SEEK_END)
            tag = encrypted_file.read(TAG_SIZE)
            ciphertext_end = encrypted_file.tell() - TAG_SIZE
            encrypted_file.seek(len(ARCHIVE_MAGIC) + NONCE_SIZE)
            decryptor = Cipher(
                algorithms.AES(encryption_key),
                modes.GCM(nonce, tag),
            ).decryptor()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with temporary_output.open("xb") as plaintext_file:
                os.fchmod(plaintext_file.fileno(), 0o600)
                remaining = ciphertext_end - encrypted_file.tell()
                while remaining:
                    chunk = encrypted_file.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise OffsiteBackupError("encrypted archive is truncated")
                    plaintext_file.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                plaintext_file.write(decryptor.finalize())
        os.replace(temporary_output, destination)
        destination.chmod(0o600)
    except Exception:
        temporary_output.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    return destination


def upload_and_verify(
    *,
    client: S3Client,
    archive_path: Path,
    bucket: str,
    object_key: str,
) -> None:
    """Upload one archive, download it again, and verify its ciphertext digest."""
    archive = Path(archive_path).resolve()
    size = archive.stat().st_size
    if size > MAX_SINGLE_UPLOAD_SIZE:
        raise OffsiteBackupError(
            "encrypted backup exceeds the provider's 5 GiB single-upload limit"
        )
    digest = _sha256(archive)
    with archive.open("rb") as encrypted_file:
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=encrypted_file,
            ContentLength=size,
            ContentType="application/octet-stream",
            Metadata={
                "sha256": digest,
                "format": "mentorconnect-offsite-v1",
            },
        )
    remote = client.head_object(Bucket=bucket, Key=object_key)
    remote_metadata = remote.get("Metadata")
    if remote.get("ContentLength") != size:
        raise OffsiteBackupError("remote backup size verification failed")
    if not isinstance(remote_metadata, dict) or remote_metadata.get("sha256") != digest:
        raise OffsiteBackupError("remote backup digest metadata verification failed")
    verification_path = archive.with_name(f".{archive.name}.remote-verify")
    verification_path.unlink(missing_ok=True)
    try:
        client.download_file(bucket, object_key, str(verification_path))
        if verification_path.stat().st_size != size:
            raise OffsiteBackupError("downloaded backup size verification failed")
        if _sha256(verification_path) != digest:
            raise OffsiteBackupError("downloaded backup digest verification failed")
    finally:
        verification_path.unlink(missing_ok=True)


def delete_expired_backup_versions(
    *,
    client: S3Client,
    bucket: str,
    prefix: str,
    cutoff: datetime,
) -> int:
    """Delete versioned backup objects older than the retention cutoff."""
    normalized_cutoff = cutoff.astimezone(timezone.utc)
    request: dict[str, object] = {"Bucket": bucket, "Prefix": prefix}
    deleted = 0
    while True:
        response = client.list_object_versions(**request)
        versions = response.get("Versions", [])
        if not isinstance(versions, list):
            raise OffsiteBackupError("S3 returned an invalid version listing")
        for version in versions:
            if not isinstance(version, dict):
                raise OffsiteBackupError("S3 returned an invalid object version")
            key = version.get("Key")
            version_id = version.get("VersionId")
            last_modified = version.get("LastModified")
            if (
                not isinstance(key, str)
                or not key.startswith(prefix)
                or not isinstance(version_id, str)
                or not isinstance(last_modified, datetime)
            ):
                continue
            if last_modified.astimezone(timezone.utc) >= normalized_cutoff:
                continue
            client.delete_object(
                Bucket=bucket,
                Key=key,
                VersionId=version_id,
            )
            deleted += 1
        if response.get("IsTruncated") is not True:
            break
        next_key = response.get("NextKeyMarker")
        next_version = response.get("NextVersionIdMarker")
        if not isinstance(next_key, str) or not isinstance(next_version, str):
            raise OffsiteBackupError("S3 omitted version pagination markers")
        request["KeyMarker"] = next_key
        request["VersionIdMarker"] = next_version
    return deleted


def _create_s3_client(*, endpoint: str, region: str, access_key: str, secret_key: str):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as error:
        raise OffsiteBackupError("boto3 is required for offsite backups") from error
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        ),
    )


def _add_bytes(
    archive: tarfile.TarFile,
    name: str,
    payload: bytes,
    created_at: datetime,
) -> None:
    import io

    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    info.mode = 0o600
    info.mtime = int(created_at.timestamp())
    archive.addfile(info, io.BytesIO(payload))


def _decode_encryption_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeError) as error:
        raise OffsiteBackupError("backup encryption key is not valid base64") from error
    _validate_encryption_key(key)
    return key


def _validate_encryption_key(key: bytes) -> None:
    if len(key) != 32:
        raise OffsiteBackupError("backup encryption key must contain exactly 32 bytes")


def _validate_sources(db_path: Path, courses_dir: Path, uploads_dir: Path) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    for directory in (courses_dir, uploads_dir):
        if not directory.is_dir():
            raise NotADirectoryError(directory)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise OffsiteBackupError(f"{name} is required")
    return value


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--courses-dir", required=True, type=Path)
    parser.add_argument("--uploads-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    archive_path: Path | None = None
    try:
        endpoint = _required_env("INTERTOP_S3_ENDPOINT")
        region = _required_env("INTERTOP_S3_REGION")
        bucket = _required_env("INTERTOP_S3_BUCKET")
        access_key = _required_env("INTERTOP_S3_ACCESS_KEY_ID")
        secret_key = _required_env("INTERTOP_S3_SECRET_ACCESS_KEY")
        encryption_key = _decode_encryption_key(
            _required_env("INTERTOP_BACKUP_ENCRYPTION_KEY")
        )
        try:
            retention_days = int(
                os.environ.get("INTERTOP_BACKUP_RETENTION_DAYS", "35")
            )
        except ValueError as error:
            raise OffsiteBackupError(
                "INTERTOP_BACKUP_RETENTION_DAYS must be an integer"
            ) from error
        if retention_days < 31:
            raise OffsiteBackupError(
                "offsite backup retention must be at least 31 days"
            )
        now = datetime.now(timezone.utc)
        name = f"mentorconnect-backup-{_timestamp(now)}.tar.gz.aes256gcm"
        archive_path = Path(args.work_dir).resolve() / name
        create_encrypted_archive(
            db_path=args.db,
            courses_dir=args.courses_dir,
            uploads_dir=args.uploads_dir,
            output_path=archive_path,
            encryption_key=encryption_key,
            clock=lambda: now,
        )
        client = _create_s3_client(
            endpoint=endpoint,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
        )
        object_key = f"daily/{name}"
        upload_and_verify(
            client=client,
            archive_path=archive_path,
            bucket=bucket,
            object_key=object_key,
        )
        deleted = delete_expired_backup_versions(
            client=client,
            bucket=bucket,
            prefix="daily/",
            cutoff=now - timedelta(days=retention_days),
        )
    except Exception as error:
        parser.exit(1, f"offsite backup failed: {error}\n")
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)

    print(f"s3://{bucket}/{object_key}")
    print(f"expired_versions_deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
