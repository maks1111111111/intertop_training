"""AI composition root.

Provides a single factory for wiring OpenAI-backed course generation
dependencies from environment configuration.
"""

from __future__ import annotations

import os
from typing import Optional

from app.ai.config import OpenAIConfig
from app.ai.openai_client import OpenAIClient
from app.ai.openai_provider import OpenAICourseGenerationAI
from app.ai.openai_review_provider import OpenAIPracticalTaskReviewer
from app.ai.review_service import PracticalTaskReviewService
from app.ai.practical_task_generation_service import PracticalTaskGenerationService
from app.ai.quiz_service import QuizGenerationService
from app.ai.service import CourseGenerationService
from app.services.course_generation_flow_service import (
    CourseGenerationFlowService,
)
from app.services.course_generation_pipeline_service import (
    CourseGenerationPipelineService,
)
from app.services.course_with_quiz_generation_service import (
    CourseWithQuizGenerationService,
)
from app.services.course_generation_persistence_service import (
    CourseGenerationPersistenceService,
)
from app.services.imported_text_generation_service import (
    ImportedTextGenerationService,
)
from app.services.practical_task_review_flow_service import (
    PracticalTaskReviewFlowService,
)
from app.services.quiz_generation_persistence_service import (
    QuizGenerationPersistenceService,
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


def create_quiz_generation_service() -> QuizGenerationService:
    """Build a :class:`QuizGenerationService` from environment config."""
    config = OpenAIConfig.from_environment()
    client = OpenAIClient(config)
    return QuizGenerationService(client)


def create_practical_task_generation_service() -> PracticalTaskGenerationService:
    """Build a :class:`PracticalTaskGenerationService` from environment config."""
    config = OpenAIConfig.from_environment()
    client = OpenAIClient(config)
    return PracticalTaskGenerationService(client)


def create_course_with_quiz_generation_service() -> CourseWithQuizGenerationService:
    """Build a :class:`CourseWithQuizGenerationService` from environment config."""
    course_persistence_service = CourseGenerationPersistenceService()
    quiz_generation_service = create_quiz_generation_service()
    quiz_persistence_service = QuizGenerationPersistenceService()
    return CourseWithQuizGenerationService(
        course_persistence_service=course_persistence_service,
        quiz_generation_service=quiz_generation_service,
        quiz_persistence_service=quiz_persistence_service,
    )


def create_practical_task_review_service() -> PracticalTaskReviewService:
    """Build a PracticalTaskReviewService from environment config."""
    config = OpenAIConfig.from_environment()
    provider = OpenAIPracticalTaskReviewer.from_config(config)
    return PracticalTaskReviewService(provider)


def create_practical_task_review_flow_service() -> PracticalTaskReviewFlowService:
    """Build a PracticalTaskReviewFlowService from environment config."""
    review_service = create_practical_task_review_service()
    return PracticalTaskReviewFlowService(review_service)


def create_optional_practical_task_review_flow_service() -> (
    Optional[PracticalTaskReviewFlowService]
):
    """Build review flow when OpenAI is configured, otherwise return ``None``.

    Missing or blank ``OPENAI_API_KEY`` means AI practical-task review is
    disabled. Other configuration errors are not masked and propagate to the
    caller.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None or not api_key.strip():
        return None
    return create_practical_task_review_flow_service()
