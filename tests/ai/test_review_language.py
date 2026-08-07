"""Tests for AI review language resolution (``app.ai.review_language``)."""

from __future__ import annotations

import unittest

from app.ai.review_language import (
    normalize_review_language,
    resolve_review_language,
)


class NormalizeReviewLanguageTests(unittest.TestCase):
    def test_supported_codes_are_normalized(self) -> None:
        self.assertEqual(normalize_review_language("ru"), "ru")
        self.assertEqual(normalize_review_language(" RU "), "ru")
        self.assertEqual(normalize_review_language("en"), "en")
        self.assertEqual(normalize_review_language("kk"), "kk")

    def test_invalid_values_return_none(self) -> None:
        self.assertIsNone(normalize_review_language(""))
        self.assertIsNone(normalize_review_language("   "))
        self.assertIsNone(normalize_review_language("active"))
        self.assertIsNone(normalize_review_language("123"))


class ResolveReviewLanguageTests(unittest.TestCase):
    def test_course_language_has_priority(self) -> None:
        self.assertEqual(
            resolve_review_language(
                "en",
                "Осмотрите рабочую зону",
                "Проверка",
                "Описание",
                "Результат",
            ),
            "en",
        )

    def test_invalid_course_language_falls_back_to_task_text(self) -> None:
        self.assertEqual(
            resolve_review_language(
                "",
                "Safety Basics",
                "Inspect the work area",
                "Walk through the area.",
                "Hazards addressed.",
            ),
            "en",
        )

    def test_cyrillic_task_text_resolves_to_russian(self) -> None:
        self.assertEqual(
            resolve_review_language(
                "",
                "Основы безопасности",
                "Проверка рабочей зоны",
                "Осмотрите зону.",
                "Все риски устранены.",
            ),
            "ru",
        )

    def test_kazakh_specific_letters_resolve_to_kazakh(self) -> None:
        self.assertEqual(
            resolve_review_language(
                "",
                "Сабақ",
                "Жұмыс орнын тексеру",
                "Аудitorияны қараңыз.",
                "Қауіптер тіркелді.",
            ),
            "kk",
        )

    def test_empty_task_text_defaults_to_russian(self) -> None:
        self.assertEqual(resolve_review_language("", "", "", "", ""), "ru")


if __name__ == "__main__":
    unittest.main()
