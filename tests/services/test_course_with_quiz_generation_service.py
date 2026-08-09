"""Tests for the course-with-quiz generation application service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, call

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationRequest,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.ai.quiz_service import QuizGenerationService
from app.content.lesson_builder import LessonCandidate
from app.services.course_generation_persistence_service import (
    CourseGenerationPersistenceService,
)
from app.services.course_with_quiz_generation_service import (
    CourseWithQuizGenerationResult,
    CourseWithQuizGenerationService,
    _is_safe_course_directory,
    _safe_remove_course_directory,
)
from app.services.quiz_generation_persistence_service import (
    QuizGenerationPersistenceService,
)


class CourseWithQuizGenerationServiceTests(unittest.TestCase):
    """Tests for :class:`CourseWithQuizGenerationService`."""

    def setUp(self) -> None:
        self.lesson_one = LessonCandidate(
            title="First lesson",
            content="Content one.",
        )
        self.lesson_two = LessonCandidate(
            title="Second lesson",
            content="Content two.",
        )
        self.lesson_result = LessonGenerationResult(
            lessons=[self.lesson_one, self.lesson_two],
            course=GeneratedCourseMetadata(
                language="ru",
                title="Safety Training",
                description="Introductory safety course.",
            ),
        )
        self.quiz_result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Final course quiz",
                passing_score=80,
                questions=(
                    QuizQuestion(
                        id="q1",
                        lesson="lesson_01",
                        question="What should an employee do?",
                        options=(
                            QuizOption(id="a", text="Correct", correct=True),
                            QuizOption(id="b", text="Wrong", correct=False),
                            QuizOption(id="c", text="Wrong", correct=False),
                            QuizOption(id="d", text="Wrong", correct=False),
                        ),
                    ),
                ),
            ),
        )
        self.destination = Path("/tmp/courses")
        self.course_directory = Path("/tmp/courses/safety-training")
        self.quiz_path = Path("/tmp/courses/safety-training/quiz.json")

    def _build_service(
        self,
        course_persistence: MagicMock | None = None,
        quiz_generation: MagicMock | None = None,
        quiz_persistence: MagicMock | None = None,
    ) -> tuple[CourseWithQuizGenerationService, MagicMock, MagicMock, MagicMock]:
        mock_course_persistence = (
            course_persistence
            if course_persistence is not None
            else MagicMock(spec=CourseGenerationPersistenceService)
        )
        mock_quiz_generation = (
            quiz_generation
            if quiz_generation is not None
            else MagicMock(spec=QuizGenerationService)
        )
        mock_quiz_persistence = (
            quiz_persistence
            if quiz_persistence is not None
            else MagicMock(spec=QuizGenerationPersistenceService)
        )

        service = CourseWithQuizGenerationService(
            course_persistence_service=mock_course_persistence,
            quiz_generation_service=mock_quiz_generation,
            quiz_persistence_service=mock_quiz_persistence,
        )
        return (
            service,
            mock_course_persistence,
            mock_quiz_generation,
            mock_quiz_persistence,
        )

    def test_injected_dependencies_are_stored(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()

        self.assertIs(service._course_persistence_service, mock_course)
        self.assertIs(service._quiz_generation_service, mock_quiz_gen)
        self.assertIs(service._quiz_persistence_service, mock_quiz_persist)

    def test_course_persistence_called_once(self) -> None:
        service, mock_course, _, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory

        service.generate_and_persist(self.lesson_result, self.destination)

        mock_course.persist.assert_called_once_with(
            self.lesson_result,
            self.destination,
        )

    def test_course_persistence_receives_original_lesson_result(self) -> None:
        service, mock_course, _, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory

        service.generate_and_persist(self.lesson_result, self.destination)

        call_args = mock_course.persist.call_args
        self.assertIs(call_args.args[0], self.lesson_result)

    def test_course_persistence_receives_original_destination(self) -> None:
        service, mock_course, _, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory

        service.generate_and_persist(self.lesson_result, self.destination)

        call_args = mock_course.persist.call_args
        self.assertIs(call_args.args[1], self.destination)

    def test_quiz_request_contains_lessons_from_lesson_result(self) -> None:
        service, mock_course, mock_quiz_gen, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result

        service.generate_and_persist(self.lesson_result, self.destination)

        quiz_request = mock_quiz_gen.generate_quiz.call_args.args[0]
        self.assertEqual(
            quiz_request.lessons,
            (self.lesson_one, self.lesson_two),
        )

    def test_quiz_request_lessons_are_tuple(self) -> None:
        service, mock_course, mock_quiz_gen, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result

        service.generate_and_persist(self.lesson_result, self.destination)

        quiz_request = mock_quiz_gen.generate_quiz.call_args.args[0]
        self.assertIsInstance(quiz_request, QuizGenerationRequest)
        self.assertIsInstance(quiz_request.lessons, tuple)

    def test_quiz_request_preserves_lesson_order(self) -> None:
        service, mock_course, mock_quiz_gen, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result

        service.generate_and_persist(self.lesson_result, self.destination)

        quiz_request = mock_quiz_gen.generate_quiz.call_args.args[0]
        self.assertIs(quiz_request.lessons[0], self.lesson_one)
        self.assertIs(quiz_request.lessons[1], self.lesson_two)

    def test_quiz_generation_called_once(self) -> None:
        service, mock_course, mock_quiz_gen, _ = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result

        service.generate_and_persist(self.lesson_result, self.destination)

        mock_quiz_gen.generate_quiz.assert_called_once()

    def test_quiz_persistence_called_once(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        service.generate_and_persist(self.lesson_result, self.destination)

        mock_quiz_persist.persist.assert_called_once()

    def test_quiz_persistence_receives_quiz_result(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        service.generate_and_persist(self.lesson_result, self.destination)

        call_args = mock_quiz_persist.persist.call_args
        self.assertIs(call_args.args[0], self.quiz_result)

    def test_quiz_persistence_receives_course_directory(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        service.generate_and_persist(self.lesson_result, self.destination)

        call_args = mock_quiz_persist.persist.call_args
        self.assertIs(call_args.args[1], self.course_directory)

    def test_returns_course_with_quiz_generation_result(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        result = service.generate_and_persist(self.lesson_result, self.destination)

        self.assertIsInstance(result, CourseWithQuizGenerationResult)
        self.assertEqual(result.course_directory, self.course_directory)
        self.assertEqual(result.quiz_path, self.quiz_path)

    def test_result_preserves_original_lesson_result(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        result = service.generate_and_persist(self.lesson_result, self.destination)

        self.assertIs(result.lesson_result, self.lesson_result)

    def test_result_preserves_quiz_result_object(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        result = service.generate_and_persist(self.lesson_result, self.destination)

        self.assertIs(result.quiz_result, self.quiz_result)

    def test_call_order_is_course_then_quiz_generation_then_quiz_persistence(
        self,
    ) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        manager = MagicMock()
        manager.attach_mock(mock_course, "course")
        manager.attach_mock(mock_quiz_gen, "quiz_gen")
        manager.attach_mock(mock_quiz_persist, "quiz_persist")

        service.generate_and_persist(self.lesson_result, self.destination)

        self.assertEqual(
            manager.mock_calls,
            [
                call.course.persist(self.lesson_result, self.destination),
                call.quiz_gen.generate_quiz(ANY),
                call.quiz_persist.persist(self.quiz_result, self.course_directory),
            ],
        )

    def test_course_persistence_exception_is_propagated(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.side_effect = OSError("disk full")

        with self.assertRaises(OSError):
            service.generate_and_persist(self.lesson_result, self.destination)

        mock_quiz_gen.generate_quiz.assert_not_called()
        mock_quiz_persist.persist.assert_not_called()

    def test_quiz_generation_exception_is_propagated(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.side_effect = RuntimeError("AI failed")

        with self.assertRaises(RuntimeError):
            service.generate_and_persist(self.lesson_result, self.destination)

        mock_quiz_persist.persist.assert_not_called()

    def test_quiz_persistence_exception_is_propagated(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.side_effect = OSError("write failed")

        with self.assertRaises(OSError):
            service.generate_and_persist(self.lesson_result, self.destination)

    def test_skips_quiz_generation_when_disabled(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory

        result = service.generate_and_persist(
            self.lesson_result,
            self.destination,
            generate_quiz=False,
        )

        self.assertIsNone(result.quiz_path)
        self.assertIsNone(result.quiz_result)
        mock_quiz_gen.generate_quiz.assert_not_called()
        mock_quiz_persist.persist.assert_not_called()

    def test_passes_questions_per_lesson_to_quiz_request(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        service.generate_and_persist(
            self.lesson_result,
            self.destination,
            questions_per_lesson=0,
        )

        quiz_request = mock_quiz_gen.generate_quiz.call_args.args[0]
        self.assertEqual(quiz_request.questions_per_lesson, 0)

    def test_lesson_result_is_not_mutated(self) -> None:
        service, mock_course, mock_quiz_gen, mock_quiz_persist = self._build_service()
        mock_course.persist.return_value = self.course_directory
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist.persist.return_value = self.quiz_path

        original_lessons = list(self.lesson_result.lessons)
        service.generate_and_persist(self.lesson_result, self.destination)

        self.assertEqual(self.lesson_result.lessons, original_lessons)


class CourseWithQuizGenerationRollbackTests(unittest.TestCase):
    """Rollback tests using real temporary directories."""

    def setUp(self) -> None:
        self.lesson_one = LessonCandidate(
            title="First lesson",
            content="Content one.",
        )
        self.lesson_result = LessonGenerationResult(
            lessons=[self.lesson_one],
            course=GeneratedCourseMetadata(
                language="ru",
                title="Safety Training",
                description="Introductory safety course.",
            ),
        )
        self.quiz_result = QuizGenerationResult(
            quiz=GeneratedQuiz(
                title="Final course quiz",
                passing_score=80,
                questions=(
                    QuizQuestion(
                        id="q1",
                        lesson="lesson_01",
                        question="What should an employee do?",
                        options=(
                            QuizOption(id="a", text="Correct", correct=True),
                            QuizOption(id="b", text="Wrong", correct=False),
                            QuizOption(id="c", text="Wrong", correct=False),
                            QuizOption(id="d", text="Wrong", correct=False),
                        ),
                    ),
                ),
            ),
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.destination = Path(self.temp_dir.name) / "courses"
        self.destination.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _persist_creates_directory(
        self,
        destination: Path,
        slug: str = "generated-course",
    ) -> MagicMock:
        def _persist(_result: LessonGenerationResult, dest: Path) -> Path:
            course_dir = dest / slug
            course_dir.mkdir(parents=True, exist_ok=True)
            (course_dir / "course.json").write_text(
                f'{{"slug": "{slug}"}}',
                encoding="utf-8",
            )
            return course_dir

        mock_course_persistence = MagicMock(spec=CourseGenerationPersistenceService)
        mock_course_persistence.persist.side_effect = _persist
        return mock_course_persistence

    def _build_service(
        self,
        course_persistence: MagicMock,
        *,
        quiz_generation: MagicMock | None = None,
        quiz_persistence: MagicMock | None = None,
    ) -> tuple[CourseWithQuizGenerationService, MagicMock, MagicMock]:
        mock_quiz_generation = (
            quiz_generation
            if quiz_generation is not None
            else MagicMock(spec=QuizGenerationService)
        )
        mock_quiz_persistence = (
            quiz_persistence
            if quiz_persistence is not None
            else MagicMock(spec=QuizGenerationPersistenceService)
        )
        service = CourseWithQuizGenerationService(
            course_persistence_service=course_persistence,
            quiz_generation_service=mock_quiz_generation,
            quiz_persistence_service=mock_quiz_persistence,
        )
        return service, mock_quiz_generation, mock_quiz_persistence

    def test_empty_lessons_rolls_back_created_course_directory(self) -> None:
        empty_result = LessonGenerationResult(lessons=[])
        mock_course = self._persist_creates_directory(self.destination, slug="empty-course")
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        service, _, mock_quiz_persist = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )
        course_directory = self.destination / "empty-course"
        unrelated_directory = self.destination / "existing-course"
        unrelated_directory.mkdir()
        (unrelated_directory / "course.json").write_text(
            '{"slug": "existing-course"}',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValueError,
            "Cannot generate quiz for a course without lessons.",
        ):
            service.generate_and_persist(empty_result, self.destination)

        mock_course.persist.assert_called_once_with(empty_result, self.destination)
        self.assertFalse(course_directory.exists())
        self.assertTrue(unrelated_directory.is_dir())
        mock_quiz_gen.generate_quiz.assert_not_called()
        mock_quiz_persist.persist.assert_not_called()

    def test_quiz_generation_failure_deletes_created_course_directory(self) -> None:
        mock_course = self._persist_creates_directory(self.destination)
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_gen.generate_quiz.side_effect = RuntimeError("AI failed")
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        service, _, mock_quiz_persist = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )
        course_directory = self.destination / "generated-course"

        with self.assertRaisesRegex(RuntimeError, "AI failed"):
            service.generate_and_persist(self.lesson_result, self.destination)

        self.assertFalse(course_directory.exists())
        mock_quiz_persist.persist.assert_not_called()

    def test_quiz_persistence_failure_deletes_created_course_directory(self) -> None:
        mock_course = self._persist_creates_directory(self.destination)
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        mock_quiz_persist.persist.side_effect = OSError("write failed")
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )
        course_directory = self.destination / "generated-course"

        with self.assertRaisesRegex(OSError, "write failed"):
            service.generate_and_persist(self.lesson_result, self.destination)

        self.assertFalse(course_directory.exists())

    def test_generate_quiz_false_keeps_successfully_persisted_course_directory(
        self,
    ) -> None:
        mock_course = self._persist_creates_directory(self.destination)
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )
        course_directory = self.destination / "generated-course"

        result = service.generate_and_persist(
            self.lesson_result,
            self.destination,
            generate_quiz=False,
        )

        self.assertTrue(course_directory.is_dir())
        self.assertIsNone(result.quiz_path)
        mock_quiz_gen.generate_quiz.assert_not_called()
        mock_quiz_persist.persist.assert_not_called()

    def test_course_persistence_failure_does_not_delete_unrelated_directories(
        self,
    ) -> None:
        unrelated_directory = self.destination / "existing-course"
        unrelated_directory.mkdir()
        (unrelated_directory / "course.json").write_text(
            '{"slug": "existing-course"}',
            encoding="utf-8",
        )

        mock_course = MagicMock(spec=CourseGenerationPersistenceService)
        mock_course.persist.side_effect = OSError("disk full")
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )

        with self.assertRaisesRegex(OSError, "disk full"):
            service.generate_and_persist(self.lesson_result, self.destination)

        self.assertTrue(unrelated_directory.is_dir())
        mock_quiz_gen.generate_quiz.assert_not_called()
        mock_quiz_persist.persist.assert_not_called()

    def test_cleanup_refuses_to_delete_path_outside_destination(self) -> None:
        outside_root = Path(self.temp_dir.name) / "outside"
        outside_root.mkdir()
        outside_course = outside_root / "outside-course"
        outside_course.mkdir()
        (outside_course / "course.json").write_text(
            '{"slug": "outside-course"}',
            encoding="utf-8",
        )

        mock_course = MagicMock(spec=CourseGenerationPersistenceService)
        mock_course.persist.return_value = outside_course
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_gen.generate_quiz.side_effect = RuntimeError("AI failed")
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )

        with self.assertRaisesRegex(RuntimeError, "AI failed"):
            service.generate_and_persist(self.lesson_result, self.destination)

        self.assertTrue(outside_course.is_dir())

    def test_quiz_generation_exception_is_still_propagated(self) -> None:
        mock_course = self._persist_creates_directory(self.destination)
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_gen.generate_quiz.side_effect = ValueError("bad quiz request")
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
        )

        with self.assertRaisesRegex(ValueError, "bad quiz request"):
            service.generate_and_persist(self.lesson_result, self.destination)

    def test_quiz_persistence_exception_is_still_propagated(self) -> None:
        mock_course = self._persist_creates_directory(self.destination)
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        mock_quiz_persist.persist.side_effect = PermissionError("permission denied")
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )

        with self.assertRaisesRegex(PermissionError, "permission denied"):
            service.generate_and_persist(self.lesson_result, self.destination)

    def test_successful_flow_keeps_course_directory(self) -> None:
        mock_course = self._persist_creates_directory(self.destination)
        mock_quiz_gen = MagicMock(spec=QuizGenerationService)
        mock_quiz_gen.generate_quiz.return_value = self.quiz_result
        mock_quiz_persist = MagicMock(spec=QuizGenerationPersistenceService)
        quiz_path = self.destination / "generated-course" / "quiz.json"
        mock_quiz_persist.persist.return_value = quiz_path
        service, _, _ = self._build_service(
            mock_course,
            quiz_generation=mock_quiz_gen,
            quiz_persistence=mock_quiz_persist,
        )
        course_directory = self.destination / "generated-course"

        result = service.generate_and_persist(self.lesson_result, self.destination)

        self.assertTrue(course_directory.is_dir())
        self.assertEqual(result.course_directory, course_directory)
        self.assertEqual(result.quiz_path, quiz_path)

    def test_is_safe_course_directory_rejects_destination_root(self) -> None:
        self.assertFalse(
            _is_safe_course_directory(self.destination, self.destination),
        )

    def test_is_safe_course_directory_rejects_path_outside_destination(self) -> None:
        outside_directory = Path(self.temp_dir.name) / "outside-course"
        outside_directory.mkdir()

        self.assertFalse(
            _is_safe_course_directory(outside_directory, self.destination),
        )

    def test_safe_remove_course_directory_skips_outside_destination(self) -> None:
        outside_root = Path(self.temp_dir.name) / "outside"
        outside_root.mkdir()
        outside_course = outside_root / "outside-course"
        outside_course.mkdir()

        _safe_remove_course_directory(outside_course, self.destination)

        self.assertTrue(outside_course.is_dir())


if __name__ == "__main__":
    unittest.main()
