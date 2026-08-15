"""Application service for end-to-end AI course generation flow.

Provides a dedicated orchestration entry point for generating lessons from
an analyzed course structure without coupling callers to pipeline internals.
"""

from __future__ import annotations

from typing import Optional

from app.ai.interfaces import LessonGenerationResult
from app.content.structure_analyzer import CourseStructure
from app.services.course_generation_pipeline_service import (
    CourseGenerationPipelineService,
)


class CourseGenerationFlowService:
    """Application-layer service for end-to-end AI lesson generation."""

    def __init__(self, pipeline_service: CourseGenerationPipelineService) -> None:
        self._pipeline_service = pipeline_service

    def generate(
        self,
        structure: CourseStructure,
        *,
        output_language: Optional[str] = None,
    ) -> LessonGenerationResult:
        """Generate lessons from an analyzed course structure via AI.

        Args:
            structure: Analyzed course structure from the import pipeline.
            output_language: Optional ISO 639-1 code (ru, kk, en) for generated
                human-readable content.

        Returns:
            The :class:`LessonGenerationResult` from the generation pipeline.
        """
        return self._pipeline_service.generate_lessons(
            structure,
            output_language=output_language,
        )
