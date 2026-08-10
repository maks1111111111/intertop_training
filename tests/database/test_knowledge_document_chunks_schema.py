"""Tests for knowledge_document_chunks table schema and migration."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.database.migrations import migrate_knowledge_document_chunks_table

EXPECTED_COLUMNS = (
    "id",
    "company_id",
    "document_id",
    "chunk_index",
    "text",
    "start_char",
    "end_char",
    "created_at",
)

EXPECTED_INDEXES = (
    "idx_knowledge_document_chunks_company_id",
    "idx_knowledge_document_chunks_company_document",
    "idx_knowledge_document_chunks_company_document_index",
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


def _insert_chunk(
    connection: sqlite3.Connection,
    *,
    company_id: str = "company-a",
    document_id: str = "doc-001",
    chunk_index: int = 0,
    text: str = "First chunk text",
    start_char: int = 0,
    end_char: int = 16,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO knowledge_document_chunks (
            company_id,
            document_id,
            chunk_index,
            text,
            start_char,
            end_char
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            document_id,
            chunk_index,
            text,
            start_char,
            end_char,
        ),
    )
    return int(cursor.lastrowid)


class KnowledgeDocumentChunksSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_initialize_database_creates_table(self) -> None:
        with get_connection(self.db_path) as connection:
            self.assertTrue(
                _table_exists(connection, "knowledge_document_chunks")
            )

    def test_table_contains_expected_columns(self) -> None:
        with get_connection(self.db_path) as connection:
            columns = _column_names(connection, "knowledge_document_chunks")

        self.assertEqual(columns, list(EXPECTED_COLUMNS))

    def test_chunk_index_constraint_rejects_negative(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_chunk(connection, chunk_index=-1)

    def test_start_char_constraint_rejects_negative(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_chunk(connection, start_char=-1)

    def test_end_char_constraint_rejects_equal_to_start(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_chunk(connection, start_char=5, end_char=5)

    def test_unique_company_document_chunk_index_enforced(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_chunk(connection, chunk_index=0)
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_chunk(
                    connection,
                    chunk_index=0,
                    text="Duplicate index chunk",
                )

    def test_same_document_id_allowed_for_different_companies(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_chunk(
                connection,
                company_id="company-a",
                document_id="shared-doc",
                chunk_index=0,
            )
            _insert_chunk(
                connection,
                company_id="company-b",
                document_id="shared-doc",
                chunk_index=0,
                text="Other company chunk",
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_document_chunks"
            ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_indexes_exist(self) -> None:
        with get_connection(self.db_path) as connection:
            index_names = _index_names(connection, "knowledge_document_chunks")

        for expected_name in EXPECTED_INDEXES:
            self.assertIn(expected_name, index_names)

    def test_created_at_default_populated(self) -> None:
        with get_connection(self.db_path) as connection:
            row_id = _insert_chunk(connection)
            row = connection.execute(
                """
                SELECT created_at
                FROM knowledge_document_chunks
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertTrue(row[0])

    def test_initialize_database_is_idempotent(self) -> None:
        with get_connection(self.db_path) as connection:
            _insert_chunk(connection)

        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            self.assertTrue(
                _table_exists(connection, "knowledge_document_chunks")
            )
            for expected_name in EXPECTED_INDEXES:
                self.assertIn(
                    expected_name,
                    _index_names(connection, "knowledge_document_chunks"),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_document_chunks"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_migration_adds_indexes_to_legacy_table_without_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-chunks.db"
            connection = sqlite3.connect(db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE knowledge_document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    start_char INTEGER NOT NULL,
                    end_char INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK (chunk_index >= 0),
                    CHECK (start_char >= 0),
                    CHECK (end_char > start_char)
                );
                """
            )
            row_id = _insert_chunk(
                connection,
                company_id="legacy-company",
                document_id="legacy-doc",
                text="Legacy chunk",
            )
            connection.commit()

            self.assertEqual(
                _index_names(connection, "knowledge_document_chunks"),
                [],
            )

            migrate_knowledge_document_chunks_table(connection)
            connection.commit()

            index_names = _index_names(connection, "knowledge_document_chunks")
            for expected_name in EXPECTED_INDEXES:
                self.assertIn(expected_name, index_names)

            row = connection.execute(
                """
                SELECT company_id, document_id, text
                FROM knowledge_document_chunks
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "legacy-company")
            self.assertEqual(row[1], "legacy-doc")
            self.assertEqual(row[2], "Legacy chunk")

            migrate_knowledge_document_chunks_table(connection)
            connection.commit()

            for expected_name in EXPECTED_INDEXES:
                self.assertIn(
                    expected_name,
                    _index_names(connection, "knowledge_document_chunks"),
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_document_chunks"
            ).fetchone()[0]
            connection.close()

        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
