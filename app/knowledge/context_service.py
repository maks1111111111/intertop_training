"""Application service composing knowledge retrieval with context building."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.knowledge.context_builder import (
    KnowledgeContextBuildingOptions,
    KnowledgeRetrievalContext,
    KnowledgeRetrievalContextBuilder,
)
from app.knowledge.retrieval import KnowledgeChunkRetrievalService


class KnowledgeRetrievalContextService:
    """Orchestrate tenant-scoped retrieval and bounded context assembly."""

    def __init__(
        self,
        retrieval_service: Optional[KnowledgeChunkRetrievalService] = None,
        context_builder: Optional[KnowledgeRetrievalContextBuilder] = None,
    ) -> None:
        self._retrieval_service = (
            retrieval_service if retrieval_service is not None
            else KnowledgeChunkRetrievalService()
        )
        self._context_builder = (
            context_builder if context_builder is not None
            else KnowledgeRetrievalContextBuilder()
        )

    def build_context(
        self,
        db_path: Path,
        *,
        company_id: str,
        query: str,
        retrieval_limit: Optional[int] = None,
        options: Optional[KnowledgeContextBuildingOptions] = None,
    ) -> KnowledgeRetrievalContext:
        resolved_options = options or KnowledgeContextBuildingOptions()
        resolved_retrieval_limit = (
            retrieval_limit
            if retrieval_limit is not None
            else resolved_options.max_sources
        )

        results = self._retrieval_service.search(
            db_path,
            company_id=company_id,
            query=query,
            limit=resolved_retrieval_limit,
        )

        return self._context_builder.build(
            company_id=company_id,
            query=query,
            results=results,
            options=resolved_options,
        )
