"""Persistence layer for Knowledge Base document chunks."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Sequence, Union

from app.database.db import get_connection
from app.knowledge.chunking import KnowledgeChunk
from app.knowledge.models import KnowledgeDocumentChunk, KnowledgeDocumentChunkInput

ChunkInput = Union[KnowledgeDocumentChunkInput, KnowledgeChunk]


def _row_to_chunk(row: sqlite3.Row) -> KnowledgeDocumentChunk:
    return KnowledgeDocumentChunk(
        id=int(row["id"]),
        company_id=str(row["company_id"]),
        document_id=str(row["document_id"]),
        chunk_index=int(row["chunk_index"]),
        text=str(row["text"]),
        start_char=int(row["start_char"]),
        end_char=int(row["end_char"]),
        created_at=str(row["created_at"]),
    )


def _validate_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_chunk_input(chunk: ChunkInput) -> KnowledgeDocumentChunkInput:
    if isinstance(chunk, KnowledgeChunk):
        return KnowledgeDocumentChunkInput(
            chunk_index=chunk.index,
            text=chunk.text,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
        )
    if isinstance(chunk, KnowledgeDocumentChunkInput):
        return chunk
    raise TypeError(
        "Each chunk must be KnowledgeDocumentChunkInput or KnowledgeChunk"
    )


def _validate_chunk_input(chunk: KnowledgeDocumentChunkInput) -> KnowledgeDocumentChunkInput:
    if chunk.chunk_index < 0:
        raise ValueError("chunk_index must be non-negative")

    normalized_text = chunk.text.strip()
    if not normalized_text:
        raise ValueError("chunk text must not be empty")

    if chunk.start_char < 0:
        raise ValueError("start_char must be non-negative")

    if chunk.end_char <= chunk.start_char:
        raise ValueError("end_char must be greater than start_char")

    return KnowledgeDocumentChunkInput(
        chunk_index=chunk.chunk_index,
        text=normalized_text,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
    )


def _validate_chunk_inputs(
    chunks: Sequence[ChunkInput],
) -> tuple[KnowledgeDocumentChunkInput, ...]:
    normalized = [_validate_chunk_input(_normalize_chunk_input(chunk)) for chunk in chunks]

    seen_indexes: set[int] = set()
    for chunk in normalized:
        if chunk.chunk_index in seen_indexes:
            raise ValueError(
                f"Duplicate chunk_index in replacement payload: {chunk.chunk_index}"
            )
        seen_indexes.add(chunk.chunk_index)

    return tuple(normalized)


def replace_document_chunks(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
    chunks: Iterable[ChunkInput],
) -> int:
    """Replace all chunks for one document atomically after validating input."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")
    validated_chunks = _validate_chunk_inputs(tuple(chunks))

    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        try:
            connection.execute(
                """
                DELETE FROM knowledge_document_chunks
                WHERE company_id = ?
                  AND document_id = ?
                """,
                (normalized_company_id, normalized_document_id),
            )
            for chunk in validated_chunks:
                connection.execute(
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
                        normalized_company_id,
                        normalized_document_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.start_char,
                        chunk.end_char,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return len(validated_chunks)


def list_for_document(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
) -> list[KnowledgeDocumentChunk]:
    """Return chunks for one document ordered by chunk_index ascending."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM knowledge_document_chunks
            WHERE company_id = ?
              AND document_id = ?
            ORDER BY chunk_index ASC, id ASC
            """,
            (normalized_company_id, normalized_document_id),
        ).fetchall()

    return [_row_to_chunk(row) for row in rows]


def delete_for_document(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
) -> int:
    """Delete all chunks for one company-scoped document."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM knowledge_document_chunks
            WHERE company_id = ?
              AND document_id = ?
            """,
            (normalized_company_id, normalized_document_id),
        )

    return int(cursor.rowcount)


def count_for_document(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
) -> int:
    """Return the number of chunks stored for one document."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS chunk_count
            FROM knowledge_document_chunks
            WHERE company_id = ?
              AND document_id = ?
            """,
            (normalized_company_id, normalized_document_id),
        ).fetchone()

    if row is None:
        return 0

    return int(row["chunk_count"])
