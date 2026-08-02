"""Application service for persisting AI-generated courses to the filesystem.

Orchestrates :class:`CourseWriter` and :class:`CourseFileWriter` without
coupling callers to individual persistence components.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.ai.interfaces import LessonGenerationResult
from app.content.course_file_writer import CourseFileWriter
from app.content.course_writer import CourseWriter


class CourseGenerationPersistenceService:
    """Persist AI lesson generation results as Content Engine course files."""

    def __init__(
        self,
        course_writer: Optional[CourseWriter] = None,
        course_file_writer: Optional[CourseFileWriter] = None,
    ) -> None:
        self._course_writer = (
            course_writer if course_writer is not None else CourseWriter()
        )
        self._course_file_writer = (
            course_file_writer
            if course_file_writer is not None
            else CourseFileWriter()
        )

    def persist(
        self,
        result: LessonGenerationResult,
        destination: Path,
    ) -> Path:
        """Write a generation result under ``destination / draft.slug``.

        Args:
            result: Parsed AI output with lessons and optional course metadata.
            destination: Parent directory for the course (typically ``courses/``).

        Returns:
            The resolved course directory path.
        """
        draft = self._course_writer.write(result)
        return self._course_file_writer.write(
            draft,
            destination / draft.slug,
        )
