"""Tests for the quiz generation persistence application service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.content.quiz_file_writer import QuizFileWriter
from app.content.quiz_writer import QuizDraft, QuizWriter
from app.services.quiz_generation_persistence_service import (
    QuizGenerationPersistenceService,
)


class QuizGenerationPersistenceServiceTests(unittest.TestCase):
    """Tests for :class:`QuizGenerationPersistenceService`."""

    def setUp(self) -> None:
        self.result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Final course quiz",
                passing_score=80,
                questions=(
                    QuizQuestion(
                        id="q1",
                        lesson="lesson_01",
                        question="What should an employee do?",
                        options=(
                            QuizOption(id="a", text="Correct answer", correct=True),
                            QuizOption(id="b", text="Wrong one", correct=False),
                            QuizOption(id="c", text="Wrong two", correct=False),
                            QuizOption(id="d", text="Wrong three", correct=False),
                        ),
                    ),
                ),
            ),
        )
        self.draft = QuizDraft(
            id="brands_quiz",
            title="Final course quiz",
            passing_score=80,
            version=1,
            randomize_questions=True,
            randomize_options=True,
            questions=(),
        )

    def test_injected_quiz_writer_is_stored(self) -> None:
        mock_writer = MagicMock(spec=QuizWriter)
        mock_file_writer = MagicMock(spec=QuizFileWriter)

        service = QuizGenerationPersistenceService(
            quiz_writer=mock_writer,
            quiz_file_writer=mock_file_writer,
        )

        self.assertIs(service._quiz_writer, mock_writer)

    def test_injected_quiz_file_writer_is_stored(self) -> None:
        mock_writer = MagicMock(spec=QuizWriter)
        mock_file_writer = MagicMock(spec=QuizFileWriter)

        service = QuizGenerationPersistenceService(
            quiz_writer=mock_writer,
            quiz_file_writer=mock_file_writer,
        )

        self.assertIs(service._quiz_file_writer, mock_file_writer)

    def test_default_dependencies_are_created(self) -> None:
        service = QuizGenerationPersistenceService()

        self.assertIsInstance(service._quiz_writer, QuizWriter)
        self.assertIsInstance(service._quiz_file_writer, QuizFileWriter)

    def test_persist_calls_quiz_writer(self) -> None:
        mock_writer = MagicMock(spec=QuizWriter)
        mock_writer.write.return_value = self.draft
        mock_file_writer = MagicMock(spec=QuizFileWriter)
        mock_file_writer.write.return_value = Path("/tmp/courses/brands/quiz.json")

        service = QuizGenerationPersistenceService(
            quiz_writer=mock_writer,
            quiz_file_writer=mock_file_writer,
        )

        with tempfile.TemporaryDirectory() as tmp:
            course_directory = Path(tmp) / "brands"
            course_directory.mkdir()
            service.persist(self.result, course_directory)

        mock_writer.write.assert_called_once_with(
            self.result,
            "brands",
        )

    def test_persist_calls_quiz_file_writer_with_draft_and_directory(self) -> None:
        mock_writer = MagicMock(spec=QuizWriter)
        mock_writer.write.return_value = self.draft
        mock_file_writer = MagicMock(spec=QuizFileWriter)
        expected_path = Path("/tmp/courses/brands/quiz.json")
        mock_file_writer.write.return_value = expected_path

        service = QuizGenerationPersistenceService(
            quiz_writer=mock_writer,
            quiz_file_writer=mock_file_writer,
        )

        with tempfile.TemporaryDirectory() as tmp:
            course_directory = Path(tmp) / "brands"
            course_directory.mkdir()
            service.persist(self.result, course_directory)

        mock_file_writer.write.assert_called_once_with(
            self.draft,
            course_directory,
        )

    def test_persist_returns_quiz_json_path(self) -> None:
        mock_writer = MagicMock(spec=QuizWriter)
        mock_writer.write.return_value = self.draft
        mock_file_writer = MagicMock(spec=QuizFileWriter)
        expected_path = Path("/tmp/courses/brands/quiz.json")
        mock_file_writer.write.return_value = expected_path

        service = QuizGenerationPersistenceService(
            quiz_writer=mock_writer,
            quiz_file_writer=mock_file_writer,
        )

        with tempfile.TemporaryDirectory() as tmp:
            course_directory = Path(tmp) / "brands"
            course_directory.mkdir()
            quiz_path = service.persist(self.result, course_directory)

        self.assertEqual(quiz_path, expected_path)


if __name__ == "__main__":
    unittest.main()
