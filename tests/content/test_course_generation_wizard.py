"""Tests for course generation wizard foundation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.content.course_generation_wizard import (
    CourseGenerationOptions,
    CourseGenerationWizard,
    DifficultyLevel,
    Language,
    LessonSize,
    PreparedCourseGeneration,
)


class CourseGenerationOptionsTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationOptions` defaults and enums."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source_path = Path(self.temp_dir.name) / "source.pdf"
        self.source_path.write_text("sample", encoding="utf-8")

    def test_default_values(self) -> None:
        options = CourseGenerationOptions(source_path=self.source_path)

        self.assertEqual(options.source_language, Language.EN)
        self.assertEqual(options.output_language, Language.EN)
        self.assertIsNone(options.course_title)
        self.assertEqual(options.difficulty, DifficultyLevel.BEGINNER)
        self.assertEqual(options.lesson_count, 5)
        self.assertEqual(options.lesson_size, LessonSize.MEDIUM)
        self.assertFalse(options.generate_quiz)
        self.assertEqual(options.questions_per_lesson, 0)
        self.assertTrue(options.include_explanations)
        self.assertFalse(options.include_practical_tasks)
        self.assertFalse(options.include_checklists)

    def test_enum_values(self) -> None:
        self.assertEqual(Language.AUTO.value, "auto")
        self.assertEqual(Language.RU.value, "ru")
        self.assertEqual(Language.KK.value, "kk")
        self.assertEqual(Language.EN.value, "en")
        self.assertEqual(DifficultyLevel.BASIC.value, "basic")
        self.assertEqual(DifficultyLevel.EXPERT.value, "expert")
        self.assertEqual(LessonSize.LONG.value, "long")


class CourseGenerationWizardTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationWizard`."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source_path = Path(self.temp_dir.name) / "training.pdf"
        self.source_path.write_text("sample", encoding="utf-8")
        self.wizard = CourseGenerationWizard()

    def _options(self, **overrides) -> CourseGenerationOptions:
        defaults = {
            "source_path": self.source_path,
            "source_language": Language.RU,
            "output_language": Language.KK,
            "course_title": "  Retail Basics  ",
            "difficulty": DifficultyLevel.ADVANCED,
            "lesson_count": 3,
            "lesson_size": LessonSize.SHORT,
            "generate_quiz": True,
            "questions_per_lesson": 4,
            "include_explanations": False,
            "include_practical_tasks": True,
            "include_checklists": True,
        }
        defaults.update(overrides)
        return CourseGenerationOptions(**defaults)

    def test_prepare_returns_prepared_course_generation(self) -> None:
        options = self._options()

        prepared = self.wizard.prepare(options)

        self.assertIsInstance(prepared, PreparedCourseGeneration)
        self.assertEqual(prepared.source_path, self.source_path.resolve())
        self.assertEqual(prepared.source_language, Language.RU)
        self.assertEqual(prepared.output_language, Language.KK)
        self.assertEqual(prepared.course_title, "Retail Basics")
        self.assertEqual(prepared.difficulty, DifficultyLevel.ADVANCED)
        self.assertEqual(prepared.lesson_count, 3)
        self.assertEqual(prepared.lesson_size, LessonSize.SHORT)
        self.assertTrue(prepared.generate_quiz)
        self.assertEqual(prepared.questions_per_lesson, 4)
        self.assertFalse(prepared.include_explanations)
        self.assertTrue(prepared.include_practical_tasks)
        self.assertTrue(prepared.include_checklists)

    def test_prepare_without_course_title(self) -> None:
        prepared = self.wizard.prepare(self._options(course_title=None))

        self.assertIsNone(prepared.course_title)

    def test_missing_source_file_raises_file_not_found(self) -> None:
        missing_path = Path(self.temp_dir.name) / "missing.pdf"
        options = self._options(source_path=missing_path)

        with self.assertRaises(FileNotFoundError):
            self.wizard.prepare(options)

    def test_directory_source_path_raises_is_a_directory_error(self) -> None:
        directory_path = Path(self.temp_dir.name)
        options = self._options(source_path=directory_path)

        with self.assertRaises(IsADirectoryError):
            self.wizard.prepare(options)

    def test_unsupported_extension_raises_value_error(self) -> None:
        unsupported_path = Path(self.temp_dir.name) / "notes.txt"
        unsupported_path.write_text("text", encoding="utf-8")
        options = self._options(source_path=unsupported_path)

        with self.assertRaises(ValueError):
            self.wizard.prepare(options)

    def test_empty_course_title_raises_value_error(self) -> None:
        options = self._options(course_title="   ")

        with self.assertRaises(ValueError):
            self.wizard.prepare(options)

    def test_invalid_lesson_count_raises_value_error(self) -> None:
        options = self._options(lesson_count=0)

        with self.assertRaises(ValueError):
            self.wizard.prepare(options)

    def test_bool_lesson_count_raises_value_error(self) -> None:
        options = self._options(lesson_count=True)

        with self.assertRaises(ValueError):
            self.wizard.prepare(options)

    def test_generate_quiz_disabled_requires_zero_questions(self) -> None:
        prepared = self.wizard.prepare(
            self._options(generate_quiz=False, questions_per_lesson=0)
        )

        self.assertFalse(prepared.generate_quiz)
        self.assertEqual(prepared.questions_per_lesson, 0)

    def test_generate_quiz_disabled_with_non_zero_questions_raises(self) -> None:
        options = self._options(generate_quiz=False, questions_per_lesson=3)

        with self.assertRaises(ValueError):
            self.wizard.prepare(options)

    def test_generate_quiz_enabled_allows_adaptive_zero_questions(self) -> None:
        prepared = self.wizard.prepare(
            self._options(generate_quiz=True, questions_per_lesson=0)
        )

        self.assertTrue(prepared.generate_quiz)
        self.assertEqual(prepared.questions_per_lesson, 0)

    def test_generate_quiz_enabled_rejects_negative_questions(self) -> None:
        options = self._options(generate_quiz=True, questions_per_lesson=-1)

        with self.assertRaises(ValueError):
            self.wizard.prepare(options)


if __name__ == "__main__":
    unittest.main()
