"""Persistence layer for Knowledge Base documents."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Union

from app.database.db import get_connection
from app.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)

_ALLOWED_STATUSES = frozenset(
    status.value for status in KnowledgeDocumentStatus
)
_ALLOWED_SOURCE_TYPES = frozenset(
    source_type.value for source_type in KnowledgeSourceType
)


def _row_to_document(row: sqlite3.Row) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=int(row["id"]),
        company_id=str(row["company_id"]),
        document_id=str(row["document_id"]),
        title=str(row["title"]),
        original_filename=str(row["original_filename"]),
        source_type=KnowledgeSourceType(str(row["source_type"])),
        source_language=str(row["source_language"]),
        extracted_text=str(row["extracted_text"]),
        status=KnowledgeDocumentStatus(str(row["status"])),
        version=int(row["version"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _normalize_source_type(source_type: Union[KnowledgeSourceType, str]) -> str:
    if isinstance(source_type, KnowledgeSourceType):
        return source_type.value
    normalized = str(source_type).strip().lower()
    if normalized not in _ALLOWED_SOURCE_TYPES:
        raise ValueError(
            f"Unsupported knowledge source type: {source_type!r}"
        )
    return normalized


def _normalize_status(status: Union[KnowledgeDocumentStatus, str]) -> str:
    if isinstance(status, KnowledgeDocumentStatus):
        return status.value
    normalized = str(status).strip().lower()
    if normalized not in _ALLOWED_STATUSES:
        raise ValueError(f"Unsupported knowledge document status: {status!r}")
    return normalized


def _validate_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def create_document(
    db_path: Path,
    *,
    company_id: str,
    title: str,
    original_filename: str,
    source_type: Union[KnowledgeSourceType, str],
    source_language: str = "auto",
    extracted_text: str = "",
) -> KnowledgeDocument:
    """Create a new draft knowledge document scoped to a company."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_title = _validate_non_empty(title, "title")
    normalized_filename = _validate_non_empty(
        original_filename,
        "original_filename",
    )
    normalized_source_type = _normalize_source_type(source_type)
    normalized_source_language = _validate_non_empty(
        source_language,
        "source_language",
    )
    document_id = uuid.uuid4().hex

    with get_connection(db_path) as connection:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', 1)
            """,
            (
                normalized_company_id,
                document_id,
                normalized_title,
                normalized_filename,
                normalized_source_type,
                normalized_source_language,
                extracted_text,
            ),
        )
        row = connection.execute(
            """
            SELECT *
            FROM knowledge_documents
            WHERE id = ?
            """,
            (int(cursor.lastrowid),),
        ).fetchone()

    if row is None:
        raise RuntimeError("Failed to load created knowledge document")

    return _row_to_document(row)


def get_by_document_id(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
) -> Optional[KnowledgeDocument]:
    """Return a document only when both company_id and document_id match."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM knowledge_documents
            WHERE company_id = ?
              AND document_id = ?
            """,
            (normalized_company_id, normalized_document_id),
        ).fetchone()

    if row is None:
        return None

    return _row_to_document(row)


def list_for_company(
    db_path: Path,
    *,
    company_id: str,
    status: Optional[Union[KnowledgeDocumentStatus, str]] = None,
) -> list[KnowledgeDocument]:
    """List knowledge documents for one company, optionally filtered by status."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")

    query = """
        SELECT *
        FROM knowledge_documents
        WHERE company_id = ?
    """
    params: list[str] = [normalized_company_id]

    if status is not None:
        normalized_status = _normalize_status(status)
        query += " AND status = ?"
        params.append(normalized_status)

    query += " ORDER BY created_at DESC, id DESC"

    with get_connection(db_path) as connection:
        rows = connection.execute(query, params).fetchall()

    return [_row_to_document(row) for row in rows]


def update_extracted_text(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
    extracted_text: str,
) -> bool:
    """Update extracted text for a company-scoped document."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE knowledge_documents
            SET extracted_text = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE company_id = ?
              AND document_id = ?
            """,
            (
                extracted_text,
                normalized_company_id,
                normalized_document_id,
            ),
        )

    return cursor.rowcount > 0


def set_status(
    db_path: Path,
    *,
    company_id: str,
    document_id: str,
    status: Union[KnowledgeDocumentStatus, str],
) -> bool:
    """Update document status for a company-scoped document."""
    normalized_company_id = _validate_non_empty(company_id, "company_id")
    normalized_document_id = _validate_non_empty(document_id, "document_id")
    normalized_status = _normalize_status(status)

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE knowledge_documents
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE company_id = ?
              AND document_id = ?
            """,
            (
                normalized_status,
                normalized_company_id,
                normalized_document_id,
            ),
        )

    return cursor.rowcount > 0
