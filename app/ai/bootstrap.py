"""AI composition root.

Provides a single factory for wiring OpenAI-backed course generation
dependencies from environment configuration.
"""

from __future__ import annotations

from app.ai.config import OpenAIConfig
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.ai.service import CourseGenerationService
from app.services.course_generation_flow_service import (
    CourseGenerationFlowService,
)
from app.services.course_generation_pipeline_service import (
    CourseGenerationPipelineService,
)
from app.services.imported_text_generation_service import (
    ImportedTextGenerationService,
)


def create_course_generation_service() -> CourseGenerationService:
    """Build a :class:`CourseGenerationService` from environment config."""
    config = OpenAIConfig.from_environment()
    provider = OpenAICourseGenerationAI.from_config(config)
    return CourseGenerationService(provider)


def create_imported_text_generation_service() -> ImportedTextGenerationService:
    """Build an :class:`ImportedTextGenerationService` from environment config."""
    course_generation_service = create_course_generation_service()
    pipeline_service = CourseGenerationPipelineService(
        course_generation_service,
    )
    flow_service = CourseGenerationFlowService(
        pipeline_service,
    )
    return ImportedTextGenerationService(
        flow_service=flow_service,
    )
