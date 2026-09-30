"""Tests for tenant-scoped, secret-free company data exports."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.database.company_data_export import (
    CompanyDataExportError,
    create_company_data_export,
)
from app.database.db import initialize_database


class CompanyDataExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.db_path = self.root / "training.db"
        self.courses_dir = self.root / "courses"
        self.uploads_dir = self.root / "uploads"
        self.courses_dir.mkdir()
        self.uploads_dir.mkdir()
        initialize_database(self.db_path)
        self._seed_tenants()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _seed_tenants(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO companies (id, name) VALUES ('alpha', 'Alpha Ltd')"
            )
            connection.execute(
                "INSERT INTO companies (id, name) VALUES ('bravo', 'Bravo Ltd')"
            )
            connection.execute(
                "INSERT INTO companies (id, name) VALUES ('empty', 'Empty Ltd')"
            )
            connection.execute(
                """
                INSERT INTO users (id, username, first_name, last_name)
                VALUES (1, 'alpha-user', 'Alice', 'Alpha')
                """
            )
            connection.execute(
                """
                INSERT INTO users (id, username, first_name, last_name)
                VALUES (2, 'bravo-user', 'Bob', 'Bravo')
                """
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (user_id, email, password_hash)
                VALUES (1, 'alice@alpha.example', 'alpha-password-hash')
                """
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (user_id, email, password_hash)
                VALUES (2, 'bob@bravo.example', 'bravo-password-hash')
                """
            )
            connection.execute(
                """
                INSERT INTO user_mfa_credentials (user_id, encrypted_secret)
                VALUES (1, 'alpha-mfa-secret')
                """
            )
            connection.execute(
                """
                INSERT INTO company_memberships (company_id, user_id, role)
                VALUES ('alpha', 1, 'admin'), ('bravo', 2, 'student')
                """
            )
            connection.execute(
                """
                INSERT INTO company_departments (id, company_id, name)
                VALUES (10, 'alpha', 'Training')
                """
            )
            connection.execute(
                """
                INSERT INTO company_member_organizations
                    (company_id, user_id, department_id)
                VALUES ('alpha', 1, 10)
                """
            )
            connection.execute(
                """
                INSERT INTO company_usage_limits (company_id, max_active_members)
                VALUES ('alpha', 20)
                """
            )
            connection.execute(
                """
                INSERT INTO courses (id, company_id, slug, title)
                VALUES (20, 'alpha', 'alpha-course', 'Alpha course'),
                       (21, 'bravo', 'bravo-course', 'Bravo course')
                """
            )
            connection.execute(
                """
                INSERT INTO lessons (id, course_id, title)
                VALUES (30, 20, 'Alpha lesson'), (31, 21, 'Bravo lesson')
                """
            )
            connection.execute(
                """
                INSERT INTO enrollments (company_id, user_id, course_id)
                VALUES ('alpha', 1, 20), ('bravo', 2, 21)
                """
            )
            connection.execute(
                """
                INSERT INTO lesson_progress (company_id, user_id, lesson_id)
                VALUES ('alpha', 1, 30), ('bravo', 2, 31)
                """
            )
            connection.execute(
                """
                INSERT INTO quiz_attempts
                    (id, company_id, user_id, course_slug, quiz_version, started_at,
                     questions_count)
                VALUES (40, 'alpha', 1, 'alpha-course', 1, '2026-09-27T00:00:00Z', 1),
                       (41, 'bravo', 2, 'bravo-course', 1, '2026-09-27T00:00:00Z', 1)
                """
            )
            connection.execute(
                """
                INSERT INTO quiz_answers
                    (id, attempt_id, question_id, selected_option_id, is_correct)
                VALUES (50, 40, 'alpha-question', 'a', 1),
                       (51, 41, 'bravo-question', 'b', 0)
                """
            )
            connection.execute(
                """
                INSERT INTO practical_task_attempts
                    (company_id, user_id, course_slug, lesson_slug, task_title,
                     task_description, expected_result, learner_answer)
                VALUES ('alpha', 1, 'alpha-course', 'lesson', 'Alpha task', 'Do alpha',
                        'Alpha result', 'Alpha answer'),
                       ('bravo', 2, 'bravo-course', 'lesson', 'Bravo task', 'Do bravo',
                        'Bravo result', 'Bravo answer')
                """
            )
            connection.execute(
                """
                INSERT INTO web_lesson_progress
                    (company_id, user_id, course_slug, lesson_id)
                VALUES ('alpha', '1', 'alpha-course', 'web-alpha'),
                       ('bravo', '2', 'bravo-course', 'web-bravo')
                """
            )
            connection.execute(
                """
                INSERT INTO knowledge_documents
                    (company_id, document_id, title, original_filename, source_type)
                VALUES ('alpha', 'alpha-doc', 'Alpha guide', 'alpha.pdf', 'pdf'),
                       ('bravo', 'bravo-doc', 'Bravo guide', 'bravo.pdf', 'pdf')
                """
            )
            connection.execute(
                """
                INSERT INTO knowledge_document_chunks
                    (company_id, document_id, chunk_index, text, start_char, end_char)
                VALUES ('alpha', 'alpha-doc', 0, 'Alpha document text', 0, 19),
                       ('bravo', 'bravo-doc', 0, 'Bravo document text', 0, 19)
                """
            )
            connection.execute(
                """
                INSERT INTO platform_audit_events (action, target_type, target_id)
                VALUES ('internal', 'company', 'alpha')
                """
            )

        (self.courses_dir / "alpha").mkdir()
        (self.courses_dir / "alpha" / "alpha-course").mkdir()
        (self.courses_dir / "alpha" / "alpha-course" / "course.json").write_text(
            '{"title":"Alpha course"}', encoding="utf-8"
        )
        (self.courses_dir / "bravo").mkdir()
        (self.courses_dir / "bravo" / "bravo-course").mkdir()
        (self.courses_dir / "bravo" / "bravo-course" / "course.json").write_text(
            '{"title":"Bravo course"}', encoding="utf-8"
        )
        (self.uploads_dir / "alpha").mkdir()
        (self.uploads_dir / "alpha" / "alpha.pdf").write_bytes(b"alpha upload")
        (self.uploads_dir / "bravo").mkdir()
        (self.uploads_dir / "bravo" / "bravo.pdf").write_bytes(b"bravo upload")

    def test_export_contains_only_requested_company_and_no_authentication_secrets(self) -> None:
        output = self.root / "alpha-export.tar.gz"
        result = create_company_data_export(
            db_path=self.db_path,
            company_id="alpha",
            courses_dir=self.courses_dir,
            uploads_dir=self.uploads_dir,
            output_path=output,
            clock=lambda: datetime(2026, 9, 27, tzinfo=timezone.utc),
        )

        self.assertEqual(result.company_id, "alpha")
        self.assertEqual(len(result.archive_sha256), 64)
        self.assertTrue(result.archive_sha256.isascii())
        self.assertEqual(
            result.archive_sha256,
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        self.assertEqual(result.course_files, 1)
        self.assertEqual(result.upload_files, 1)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)

        with tarfile.open(output, mode="r:gz") as archive:
            names = archive.getnames()
            manifest = json.load(archive.extractfile("manifest.json"))
            members = json.load(archive.extractfile("data/members.json"))
            document_chunks = json.load(
                archive.extractfile("data/knowledge_document_chunks.json")
            )
            serialized = "\n".join(
                archive.extractfile(name).read().decode("utf-8", errors="replace")
                for name in names
                if name.endswith(".json")
            )

        self.assertIn("files/courses/alpha-course/course.json", names)
        self.assertIn("files/uploads/alpha.pdf", names)
        self.assertNotIn("files/courses/bravo-course/course.json", names)
        self.assertNotIn("files/uploads/bravo.pdf", names)
        self.assertEqual(manifest["company"]["id"], "alpha")
        self.assertIn("password hashes", manifest["excluded"])
        self.assertEqual(members[0]["email"], "alice@alpha.example")
        self.assertEqual(document_chunks[0]["document_id"], "alpha-doc")
        self.assertNotIn("bravo", serialized)
        self.assertNotIn("alpha-password-hash", serialized)
        self.assertNotIn("alpha-mfa-secret", serialized)
        self.assertNotIn("platform_audit_events", serialized)

    def test_unknown_company_leaves_no_export(self) -> None:
        output = self.root / "missing.tar.gz"

        with self.assertRaisesRegex(CompanyDataExportError, "company does not exist"):
            create_company_data_export(
                db_path=self.db_path,
                company_id="missing",
                courses_dir=self.courses_dir,
                uploads_dir=self.uploads_dir,
                output_path=output,
            )

        self.assertFalse(output.exists())

    def test_export_of_a_new_company_without_courses_needs_no_course_directory(self) -> None:
        output = self.root / "empty-export.tar.gz"

        result = create_company_data_export(
            db_path=self.db_path,
            company_id="empty",
            courses_dir=self.courses_dir,
            uploads_dir=self.uploads_dir,
            output_path=output,
        )

        self.assertEqual(result.company_id, "empty")
        self.assertEqual(result.course_files, 0)
        self.assertEqual(result.upload_files, 0)
        with tarfile.open(output, mode="r:gz") as archive:
            manifest = json.load(archive.extractfile("manifest.json"))
        self.assertEqual(manifest["company"]["id"], "empty")
        self.assertEqual(manifest["course_files"], 0)

    def test_refuses_a_symbolic_link_in_company_files(self) -> None:
        target = self.root / "outside.txt"
        target.write_text("outside", encoding="utf-8")
        (self.uploads_dir / "alpha" / "linked.txt").symlink_to(target)

        with self.assertRaisesRegex(CompanyDataExportError, "symbolic link"):
            create_company_data_export(
                db_path=self.db_path,
                company_id="alpha",
                courses_dir=self.courses_dir,
                uploads_dir=self.uploads_dir,
                output_path=self.root / "linked.tar.gz",
            )

    def test_refuses_a_non_private_output_directory(self) -> None:
        output_directory = self.root / "not-private"
        output_directory.mkdir(mode=0o755)

        with self.assertRaisesRegex(CompanyDataExportError, "must not grant"):
            create_company_data_export(
                db_path=self.db_path,
                company_id="alpha",
                courses_dir=self.courses_dir,
                uploads_dir=self.uploads_dir,
                output_path=output_directory / "alpha.tar.gz",
            )


if __name__ == "__main__":
    unittest.main()
