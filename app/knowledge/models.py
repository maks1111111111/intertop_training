"""Domain models for the corporate Knowledge Base."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KnowledgeDocumentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class KnowledgeSourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"


@dataclass(frozen=True)
class KnowledgeDocument:
    id: int
    company_id: str
    document_id: str
    title: str
    original_filename: str
    source_type: KnowledgeSourceType
    source_language: str
    extracted_text: str
    status: KnowledgeDocumentStatus
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class KnowledgeDocumentCreate:
    company_id: str
    title: str
    original_filename: str
    source_type: KnowledgeSourceType
    source_language: str = "auto"
    extracted_text: str = ""


@dataclass(frozen=True)
class KnowledgeDocumentChunk:
    id: int
    company_id: str
    document_id: str
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    created_at: str


@dataclass(frozen=True)
class KnowledgeDocumentChunkInput:
    """Input for persisting one knowledge document chunk."""

    chunk_index: int
    text: str
    start_char: int
    end_char: int
