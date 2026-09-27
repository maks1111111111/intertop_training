"""Tests for the non-destructive encrypted offsite restore drill."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.database.offsite_backup import create_encrypted_archive
from app.database.offsite_restore_verify import (
    OffsiteRestoreVerificationError,
    verify_latest_offsite_backup,
)


class _FakeS3Client:
    def __init__(self, objects: dict[str, tuple[datetime, bytes]]) -> None:
        self._objects = objects
        self.downloaded: list[tuple[str, str]] = []

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        prefix = str(kwargs["Prefix"])
        return {
            "IsTruncated": False,
            "Contents": [
                {"Key": key, "LastModified": modified}
                for key, (modified, _payload) in self._objects.items()
                if key.startswith(prefix)
            ],
        }

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        self.downloaded.append((bucket, key))
        Path(filename).write_bytes(self._objects[key][1])


class OffsiteRestoreVerificationTests(unittest.TestCase):
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
            connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        self.key = bytes(range(32))
        self.work_dir = self.root / "restore-drill"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _encrypted_archive(self, name: str) -> bytes:
        path = self.root / name
        create_encrypted_archive(
            db_path=self.db_path,
            courses_dir=self.courses_dir,
            uploads_dir=self.uploads_dir,
            output_path=path,
            encryption_key=self.key,
        )
        return path.read_bytes()

    def test_verifies_newest_archive_without_leaving_plaintext_behind(self) -> None:
        old_key = "daily/mentorconnect-backup-old.tar.gz.aes256gcm"
        latest_key = "daily/mentorconnect-backup-latest.tar.gz.aes256gcm"
        client = _FakeS3Client(
            {
                old_key: (
                    datetime(2026, 9, 25, tzinfo=timezone.utc),
                    self._encrypted_archive("old.enc"),
                ),
                latest_key: (
                    datetime(2026, 9, 26, tzinfo=timezone.utc),
                    self._encrypted_archive("latest.enc"),
                ),
            }
        )

        result = verify_latest_offsite_backup(
            client=client,
            bucket="private-backups",
            encryption_key=self.key,
            work_dir=self.work_dir,
        )

        self.assertEqual(result.object_key, latest_key)
        self.assertTrue(result.database_verified)
        self.assertGreater(result.course_entries, 0)
        self.assertGreater(result.upload_entries, 0)
        self.assertEqual(client.downloaded, [("private-backups", latest_key)])
        self.assertEqual(list(self.work_dir.iterdir()), [])
        self.assertEqual(self.work_dir.stat().st_mode & 0o777, 0o700)

    def test_refuses_when_no_encrypted_backup_exists(self) -> None:
        with self.assertRaisesRegex(
            OffsiteRestoreVerificationError,
            "no encrypted offsite backups",
        ):
            verify_latest_offsite_backup(
                client=_FakeS3Client({}),
                bucket="private-backups",
                encryption_key=self.key,
                work_dir=self.work_dir,
            )


if __name__ == "__main__":
    unittest.main()
