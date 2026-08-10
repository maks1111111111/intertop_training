"""Tests for knowledge_documents table schema and migration."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.migrations import migrate_knowledge_documents_table

EXPECTED_COLUMNS = (
    "id",
    "company_id",
    "document_id",
    "title",
    "original_filename",
    "source_type",
    "source_language",
    "extracted_text",
    "status",
    "version",
    "created_at",
    "updated_at",
)

EXPECTED_INDEXES = (
    "idx_knowledge_documents_company_id",
    "idx_knowledge_documents_company_status",
    "idx_knowledge_documents_company_document",
)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row[1] for row in rows]


def _index_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA index_list({table_name})").fetchall()
    return [row[1] for row in rows]


def _insert_document(
    connection: sqlite3.Connection,
    *,
    company_id: str = "company-a",
    document_id: str = "doc-001",
    title: str = "Safety Manual",
    original_filename: str = "manual.pdf",
    source_type: str = "pdf",
    source_language: str = "auto",
    extracted_text: str = "",
    status: str = "draft",
    version: int = 1,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO knowledge_documents (
            company_id,
            document_id,
            title,
            original_filename,
            source_type,
            source_language,
            extracted_text,
            status,
            version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            document_id,
            title,
            original_filename,
            source_type,
            source_language,
            extracted_text,
            status,
            version,
        ),
    )
    return int(cursor.lastrowid)


class KnowledgeDocumentsSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_initialize_database_creates_table(self) -> None:
        with get_connection(self.db_path) as connection:
            self.assertTrue(_table_exists(connection, "knowledge_documents"))

    def test_table_contains_expected_columns(self) -> None:
        with get_connection(self.db_path) as connection:
            columns = _column_names(connection, "knowledge_documents")

        self.assertEqual(columns, list(EXPECTED_COLUMNS))

    def test_source_type_constraint_rejects_unsupported_type(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_document(connection, source_type="mp4")

    def test_status_constraint_rejects_unsupported_value(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_document(connection, status="published")

    def test_version_constraint_rejects_zero(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_document(connection, version=0)

    def test_unique_company_id_and_document_id_enforced(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_document(connection, company_id="company-a", document_id="doc-001")
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_document(
                    connection,
                    company_id="company-a",
                    document_id="doc-001",
                    title="Duplicate",
                )

    def test_same_document_id_allowed_for_different_companies(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_document(connection, company_id="company-a", document_id="shared-id")
            _insert_document(
                connection,
                company_id="company-b",
                document_id="shared-id",
                title="Other company doc",
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_documents"
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_indexes_exist(self) -> None:
        with get_connection(self.db_path) as connection:
            index_names = _index_names(connection, "knowledge_documents")

        for expected_name in EXPECTED_INDEXES:
            self.assertIn(expected_name, index_names)

    def test_default_values_for_minimal_insert(self) -> None:
        with get_connection(self.db_path) as connection:
            row_id = _insert_document(connection)
            row = connection.execute(
                """
                SELECT source_language, extracted_text, status, version,
                       created_at, updated_at
                FROM knowledge_documents
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "auto")
        self.assertEqual(row[1], "")
        self.assertEqual(row[2], "draft")
        self.assertEqual(row[3], 1)
        self.assertIsNotNone(row[4])
        self.assertIsNotNone(row[5])

    def test_initialize_database_is_idempotent(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_document(connection)

        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            self.assertTrue(_table_exists(connection, "knowledge_documents"))
            for expected_name in EXPECTED_INDEXES:
                self.assertIn(
                    expected_name,
                    _index_names(connection, "knowledge_documents"),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_documents"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_existing_database_is_upgraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"

            connection = sqlite3.connect(db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                """,
                (4242, "legacy", "Legacy", "User"),
            )
            connection.commit()
            connection.close()

            initialize_database(db_path)

            with get_connection(db_path) as connection:
                self.assertTrue(_table_exists(connection, "knowledge_documents"))
                for expected_name in EXPECTED_INDEXES:
                    self.assertIn(
                        expected_name,
                        _index_names(connection, "knowledge_documents"),
                    )
                user_count = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE telegram_id = ?",
                    (4242,),
                ).fetchone()[0]

        self.assertEqual(user_count, 1)

    def test_migration_adds_indexes_to_legacy_table_without_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-knowledge.db"
            connection = sqlite3.connect(db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE knowledge_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_language TEXT NOT NULL DEFAULT 'auto',
                    extracted_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK (source_type IN ('pdf', 'docx', 'pptx')),
                    CHECK (status IN ('draft', 'active', 'archived')),
                    CHECK (version >= 1)
                );
                """
            )
            row_id = _insert_document(
                connection,
                company_id="legacy-company",
                document_id="legacy-doc",
                title="Legacy Document",
            )
            connection.commit()

            self.assertEqual(_index_names(connection, "knowledge_documents"), [])

            migrate_knowledge_documents_table(connection)
            connection.commit()

            index_names = _index_names(connection, "knowledge_documents")
            for expected_name in EXPECTED_INDEXES:
                self.assertIn(expected_name, index_names)

            row = connection.execute(
                """
                SELECT company_id, document_id, title
                FROM knowledge_documents
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "legacy-company")
            self.assertEqual(row[1], "legacy-doc")
            self.assertEqual(row[2], "Legacy Document")

            migrate_knowledge_documents_table(connection)
            connection.commit()

            for expected_name in EXPECTED_INDEXES:
                self.assertIn(
                    expected_name,
                    _index_names(connection, "knowledge_documents"),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_documents"
            ).fetchone()[0]
            connection.close()

        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
