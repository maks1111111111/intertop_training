"""AI composition root.

Provides a single factory for wiring OpenAI-backed course generation
dependencies from environment configuration.
"""

from __future__ import annotations

from app.ai.config import OpenAIConfig
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.ai.service import CourseGenerationService


def create_course_generation_service() -> CourseGenerationService:
    """Build a :class:`CourseGenerationService` from environment config."""
    config = OpenAIConfig.from_environment()
    provider = OpenAICourseGenerationAI.from_config(config)
    return CourseGenerationService(provider)
