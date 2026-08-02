"""Tests for the course generation persistence application service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.course_file_writer import CourseFileWriter
from app.content.course_writer import CourseDraft, CourseWriter
from app.content.lesson_builder import LessonCandidate
from app.services.course_generation_persistence_service import (
    CourseGenerationPersistenceService,
)


class CourseGenerationPersistenceServiceTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationPersistenceService`."""

    def setUp(self) -> None:
        self.result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="First lesson",
                    content="Content one.",
                ),
                LessonCandidate(
                    title="Second lesson",
                    content="Content two.",
                ),
            ],
            course=GeneratedCourseMetadata(
                language="ru",
                title="Safety Training",
                description="Introductory safety course.",
            ),
        )
        self.draft = CourseDraft(
            slug="safety-training",
            title="Safety Training",
            description="Introductory safety course.",
            language="ru",
            lessons=tuple(self.result.lessons),
        )

    def test_injected_course_writer_is_stored(self) -> None:
        mock_writer = MagicMock(spec=CourseWriter)
        mock_file_writer = MagicMock(spec=CourseFileWriter)

        service = CourseGenerationPersistenceService(
            course_writer=mock_writer,
            course_file_writer=mock_file_writer,
        )

        self.assertIs(service._course_writer, mock_writer)

    def test_injected_course_file_writer_is_stored(self) -> None:
        mock_writer = MagicMock(spec=CourseWriter)
        mock_file_writer = MagicMock(spec=CourseFileWriter)

        service = CourseGenerationPersistenceService(
            course_writer=mock_writer,
            course_file_writer=mock_file_writer,
        )

        self.assertIs(service._course_file_writer, mock_file_writer)

    def test_default_dependencies_are_created(self) -> None:
        service = CourseGenerationPersistenceService()

        self.assertIsInstance(service._course_writer, CourseWriter)
        self.assertIsInstance(service._course_file_writer, CourseFileWriter)

    def test_persist_calls_course_writer(self) -> None:
        mock_writer = MagicMock(spec=CourseWriter)
        mock_writer.write.return_value = self.draft
        mock_file_writer = MagicMock(spec=CourseFileWriter)
        mock_file_writer.write.return_value = Path("/tmp/courses/safety-training")

        service = CourseGenerationPersistenceService(
            course_writer=mock_writer,
            course_file_writer=mock_file_writer,
        )

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "courses"
            service.persist(self.result, destination)

        mock_writer.write.assert_called_once_with(self.result)

    def test_persist_calls_course_file_writer_with_slug_path(self) -> None:
        mock_writer = MagicMock(spec=CourseWriter)
        mock_writer.write.return_value = self.draft
        mock_file_writer = MagicMock(spec=CourseFileWriter)
        expected_path = Path("/tmp/courses/safety-training")
        mock_file_writer.write.return_value = expected_path

        service = CourseGenerationPersistenceService(
            course_writer=mock_writer,
            course_file_writer=mock_file_writer,
        )

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "courses"
            service.persist(self.result, destination)

        mock_file_writer.write.assert_called_once_with(
            self.draft,
            destination / "safety-training",
        )

    def test_persist_returns_course_directory_path(self) -> None:
        mock_writer = MagicMock(spec=CourseWriter)
        mock_writer.write.return_value = self.draft
        mock_file_writer = MagicMock(spec=CourseFileWriter)
        expected_path = Path("/tmp/courses/safety-training")
        mock_file_writer.write.return_value = expected_path

        service = CourseGenerationPersistenceService(
            course_writer=mock_writer,
            course_file_writer=mock_file_writer,
        )

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "courses"
            course_path = service.persist(self.result, destination)

        self.assertEqual(course_path, expected_path)


if __name__ == "__main__":
    unittest.main()
