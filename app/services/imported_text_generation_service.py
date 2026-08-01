"""Application service for AI lesson generation from imported text.

Provides an orchestration entry point that analyzes aggregated import text
into a course structure and delegates generation to the AI flow service.
"""

from __future__ import annotations

from typing import Optional

from app.ai.interfaces import LessonGenerationResult
from app.content.structure_analyzer import StructureAnalyzer
from app.services.course_generation_flow_service import (
    CourseGenerationFlowService,
)


class ImportedTextGenerationService:
    """Application-layer service for generating lessons from imported text."""

    def __init__(
        self,
        flow_service: CourseGenerationFlowService,
        structure_analyzer: Optional[StructureAnalyzer] = None,
    ) -> None:
        self._flow_service = flow_service
        self._structure_analyzer = (
            structure_analyzer
            if structure_analyzer is not None
            else StructureAnalyzer()
        )

    def generate_from_text(
        self,
        text: str,
    ) -> LessonGenerationResult:
        """Analyze imported text and generate lessons via the AI flow.

        Args:
            text: Aggregated text from imported documents.

        Returns:
            The :class:`LessonGenerationResult` from the generation flow.
        """
        structure = self._structure_analyzer.analyze(text)
        return self._flow_service.generate(structure)
