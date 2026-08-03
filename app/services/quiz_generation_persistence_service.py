"""Application service for persisting AI-generated quizzes to the filesystem.

Orchestrates :class:`QuizWriter` and :class:`QuizFileWriter` without coupling
callers to individual persistence components.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.ai.quiz_interfaces import QuizGenerationResult
from app.content.quiz_file_writer import QuizFileWriter
from app.content.quiz_writer import QuizWriter


class QuizGenerationPersistenceService:
    """Persist AI quiz generation results as Content Engine quiz.json files."""

    def __init__(
        self,
        quiz_writer: Optional[QuizWriter] = None,
        quiz_file_writer: Optional[QuizFileWriter] = None,
    ) -> None:
        self._quiz_writer = (
            quiz_writer if quiz_writer is not None else QuizWriter()
        )
        self._quiz_file_writer = (
            quiz_file_writer
            if quiz_file_writer is not None
            else QuizFileWriter()
        )

    def persist(
        self,
        result: QuizGenerationResult,
        course_directory: Path,
    ) -> Path:
        """Write a generation result to ``course_directory / quiz.json``.

        Args:
            result: Parsed AI quiz output.
            course_directory: Existing course root directory.

        Returns:
            The resolved path to the written ``quiz.json`` file.
        """
        draft = self._quiz_writer.write(
            result,
            course_directory.name,
        )
        return self._quiz_file_writer.write(
            draft,
            course_directory,
        )
