"""Tests for encrypted offsite application backups."""

from __future__ import annotations

import sqlite3
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.database.offsite_backup import (
    OffsiteBackupError,
    create_encrypted_archive,
    decrypt_archive,
    upload_and_verify,
)


class _FakeS3Client:
    def __init__(self) -> None:
        self.upload: tuple[str, str, str, dict[str, object]] | None = None
        self.remote_size = 0
        self.remote_metadata: dict[str, str] = {}
        self.remote_payload = b""

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, object] | None = None,
    ) -> None:
        assert ExtraArgs is not None
        self.upload = (filename, bucket, key, ExtraArgs)
        self.remote_payload = Path(filename).read_bytes()
        self.remote_size = Path(filename).stat().st_size
        metadata = ExtraArgs["Metadata"]
        assert isinstance(metadata, dict)
        self.remote_metadata = metadata

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        return {
            "ContentLength": self.remote_size,
            "Metadata": self.remote_metadata,
        }

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes(self.remote_payload)


class OffsiteBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.db_path = self.root / "training.db"
        self.courses_dir = self.root / "courses"
        self.uploads_dir = self.root / "uploads"
        self.courses_dir.mkdir()
        self.uploads_dir.mkdir()
        (self.courses_dir / "course.json").write_text(
            '{"title":"Safety"}', encoding="utf-8"
        )
        (self.uploads_dir / "manual.pdf").write_bytes(b"pdf-data")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
            connection.execute("INSERT INTO users (email) VALUES ('user@example.test')")
        self.key = bytes(range(32))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_archive_is_encrypted_and_can_be_restored_for_validation(self) -> None:
        encrypted = self.root / "backup.enc"
        plaintext = self.root / "backup.tar.gz"
        create_encrypted_archive(
            db_path=self.db_path,
            courses_dir=self.courses_dir,
            uploads_dir=self.uploads_dir,
            output_path=encrypted,
            encryption_key=self.key,
            clock=lambda: datetime(2026, 9, 26, tzinfo=timezone.utc),
        )

        self.assertEqual(encrypted.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(b"user@example.test", encrypted.read_bytes())
        decrypt_archive(encrypted, plaintext, self.key)
        with tarfile.open(plaintext, mode="r:gz") as archive:
            names = set(archive.getnames())
            self.assertIn("manifest.json", names)
            self.assertIn("database/training.db", names)
            self.assertIn("courses/course.json", names)
            self.assertIn("uploads/manual.pdf", names)

    def test_wrong_encryption_key_is_rejected_without_plaintext_output(self) -> None:
        encrypted = self.root / "backup.enc"
        plaintext = self.root / "backup.tar.gz"
        create_encrypted_archive(
            db_path=self.db_path,
            courses_dir=self.courses_dir,
            uploads_dir=self.uploads_dir,
            output_path=encrypted,
            encryption_key=self.key,
        )

        with self.assertRaises(Exception):
            decrypt_archive(encrypted, plaintext, b"x" * 32)
        self.assertFalse(plaintext.exists())

    def test_upload_verifies_remote_size_and_digest_metadata(self) -> None:
        archive = self.root / "backup.enc"
        archive.write_bytes(b"encrypted-backup")
        client = _FakeS3Client()

        upload_and_verify(
            client=client,
            archive_path=archive,
            bucket="private-backups",
            object_key="daily/backup.enc",
        )

        assert client.upload is not None
        self.assertEqual(client.upload[1:3], ("private-backups", "daily/backup.enc"))
        self.assertEqual(
            client.remote_metadata["format"],
            "mentorconnect-offsite-v1",
        )

    def test_upload_rejects_remote_size_mismatch(self) -> None:
        archive = self.root / "backup.enc"
        archive.write_bytes(b"encrypted-backup")
        client = _FakeS3Client()
        original_head = client.head_object

        def mismatched_head(*, Bucket: str, Key: str) -> dict[str, object]:
            result = original_head(Bucket=Bucket, Key=Key)
            result["ContentLength"] = 1
            return result

        client.head_object = mismatched_head  # type: ignore[method-assign]
        with self.assertRaisesRegex(OffsiteBackupError, "size verification"):
            upload_and_verify(
                client=client,
                archive_path=archive,
                bucket="private-backups",
                object_key="daily/backup.enc",
            )

    def test_upload_rejects_corrupt_downloaded_ciphertext(self) -> None:
        archive = self.root / "backup.enc"
        archive.write_bytes(b"encrypted-backup")
        client = _FakeS3Client()
        original_download = client.download_file

        def corrupt_download(bucket: str, key: str, filename: str) -> None:
            original_download(bucket, key, filename)
            Path(filename).write_bytes(b"x" * len(b"encrypted-backup"))

        client.download_file = corrupt_download  # type: ignore[method-assign]
        with self.assertRaisesRegex(OffsiteBackupError, "digest verification"):
            upload_and_verify(
                client=client,
                archive_path=archive,
                bucket="private-backups",
                object_key="daily/backup.enc",
            )


if __name__ == "__main__":
    unittest.main()
