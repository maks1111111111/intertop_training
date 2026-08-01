"""Application service for AI course generation in the import pipeline.

Orchestrates lesson candidate building and AI refinement without coupling
the import pipeline to AI provider details.
"""

from __future__ import annotations

from typing import Optional

from app.ai.interfaces import LessonGenerationRequest, LessonGenerationResult
from app.ai.service import CourseGenerationService
from app.content.lesson_builder import LessonBuilder
from app.content.structure_analyzer import CourseStructure


class CourseGenerationPipelineService:
    """Application service that builds lesson candidates and refines them via AI."""

    def __init__(
        self,
        generation_service: CourseGenerationService,
        lesson_builder: Optional[LessonBuilder] = None,
    ) -> None:
        self._generation_service = generation_service
        self._lesson_builder = (
            lesson_builder if lesson_builder is not None else LessonBuilder()
        )

    def generate_lessons(
        self,
        structure: CourseStructure,
    ) -> LessonGenerationResult:
        """Build lesson candidates from structure and refine them via AI.

        Args:
            structure: Analyzed course structure from the import pipeline.

        Returns:
            The :class:`LessonGenerationResult` from the configured AI service.
        """
        candidates = self._lesson_builder.build(structure)
        request = LessonGenerationRequest(lessons=candidates)
        return self._generation_service.generate_lessons(request)
