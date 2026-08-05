"""Tests for lesson Telegram text formatting."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.content.runtime_loader import Lesson
from app.ui.lesson import lesson_body_text, lesson_quality_sections_text


def _sample_lesson(**overrides: object) -> Lesson:
    defaults = {
        "path": Path("lesson_01"),
        "number": 1,
        "title": "Sample Lesson",
        "description": "Main lesson text.",
        "image_path": None,
        "narration_path": None,
        "practical_task": "",
        "checklist": (),
        "common_mistakes": (),
        "key_takeaways": (),
        "application_tips": (),
    }
    defaults.update(overrides)
    return Lesson(**defaults)


class LessonQualitySectionsTextTests(unittest.TestCase):
    def test_legacy_lesson_without_quality_fields_returns_empty(self) -> None:
        lesson = _sample_lesson()

        self.assertEqual(lesson_quality_sections_text(lesson), "")

    def test_practical_task_section_rendered(self) -> None:
        lesson = _sample_lesson(practical_task="Complete the safety checklist.")

        text = lesson_quality_sections_text(lesson)

        self.assertIn("🛠 Практическое задание", text)
        self.assertIn("Complete the safety checklist.", text)

    def test_whitespace_only_practical_task_is_omitted(self) -> None:
        lesson = _sample_lesson(practical_task="   ")

        self.assertEqual(lesson_quality_sections_text(lesson), "")

    def test_all_quality_sections_rendered(self) -> None:
        lesson = _sample_lesson(
            practical_task="Inspect the work area.",
            checklist=("Wear PPE", "Check equipment"),
            common_mistakes=("Skipping inspection",),
            key_takeaways=("Safety first",),
            application_tips=("Apply the checklist daily",),
        )

        text = lesson_quality_sections_text(lesson)

        self.assertIn("🛠 Практическое задание\nInspect the work area.", text)
        self.assertIn("✅ Чек-лист\n• Wear PPE\n• Check equipment", text)
        self.assertIn("⚠ Типичные ошибки\n• Skipping inspection", text)
        self.assertIn("💡 Главное запомнить\n• Safety first", text)
        self.assertIn("🚀 Советы по применению\n• Apply the checklist daily", text)

    def test_empty_tuple_sections_are_omitted(self) -> None:
        lesson = _sample_lesson(
            practical_task="Do the task.",
            checklist=(),
        )

        text = lesson_quality_sections_text(lesson)

        self.assertIn("🛠 Практическое задание", text)
        self.assertNotIn("✅ Чек-лист", text)


class LessonBodyTextTests(unittest.TestCase):
    def test_legacy_lesson_returns_description_only(self) -> None:
        lesson = _sample_lesson(description="Legacy lesson body.")

        self.assertEqual(lesson_body_text(lesson), "Legacy lesson body.")

    def test_description_followed_by_quality_sections(self) -> None:
        lesson = _sample_lesson(
            description="Main lesson text.",
            practical_task="Practice task.",
            checklist=("Step one",),
        )

        text = lesson_body_text(lesson)

        self.assertTrue(text.startswith("Main lesson text.\n\n"))
        self.assertIn("🛠 Практическое задание\nPractice task.", text)
        self.assertIn("✅ Чек-лист\n• Step one", text)

    def test_quality_sections_without_description(self) -> None:
        lesson = _sample_lesson(
            description="",
            key_takeaways=("Remember this",),
        )

        text = lesson_body_text(lesson)

        self.assertEqual(text, "💡 Главное запомнить\n• Remember this")

    def test_empty_lesson_returns_empty_string(self) -> None:
        lesson = _sample_lesson(description="")

        self.assertEqual(lesson_body_text(lesson), "")


if __name__ == "__main__":
    unittest.main()
