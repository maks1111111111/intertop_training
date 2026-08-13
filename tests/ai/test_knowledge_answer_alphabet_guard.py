"""Tests for mixed-script detection and homoglyph normalization."""

from __future__ import annotations

import unittest

from app.ai.knowledge_answer_alphabet_guard import (
    has_unfixable_mixed_alphabet,
    normalize_answer_alphabet,
    normalize_word_homoglyphs,
    needs_alphabet_rewrite,
    word_has_mixed_scripts,
)
from app.ai.knowledge_answer_language_guard import needs_language_rewrite


class NormalizeWordHomoglyphsTests(unittest.TestCase):
    def test_fixes_latin_homoglyphs_in_cyrillic_word(self) -> None:
        self.assertEqual(normalize_word_homoglyphs("контрol"), "контрол")

    def test_fixes_common_service_word_homoglyphs(self) -> None:
        normalized = normalize_word_homoglyphs("Сервicenые")
        self.assertFalse(word_has_mixed_scripts(normalized))

    def test_leaves_pure_latin_word_unchanged(self) -> None:
        self.assertEqual(normalize_word_homoglyphs("Intertop"), "Intertop")


class NormalizeAnswerAlphabetTests(unittest.TestCase):
    def test_normalizes_mixed_homoglyph_word_in_sentence(self) -> None:
        answer = "Проверьте контрol качества перед открытием смены."
        normalized = normalize_answer_alphabet(answer, "ru")

        self.assertIn("контрол", normalized)
        self.assertNotIn("контрol", normalized)

    def test_clean_russian_answer_unchanged(self) -> None:
        answer = "Сервисные стандарты обслуживания состоят из семи этапов."
        self.assertEqual(normalize_answer_alphabet(answer, "ru"), answer)

    def test_english_answer_not_modified(self) -> None:
        answer = "Service standards include seven stages."
        self.assertEqual(normalize_answer_alphabet(answer, "en"), answer)


class MixedAlphabetDetectionTests(unittest.TestCase):
    def test_detects_unfixable_mixed_word_with_digits(self) -> None:
        self.assertTrue(
            has_unfixable_mixed_alphabet("Серв1cenые стандарты", "ru")
        )

    def test_no_unfixable_mixed_after_homoglyph_normalization(self) -> None:
        self.assertFalse(
            has_unfixable_mixed_alphabet("Сервicenые стандарты", "ru")
        )

    def test_word_has_mixed_scripts(self) -> None:
        self.assertTrue(word_has_mixed_scripts("Сервicenые"))
        self.assertFalse(word_has_mixed_scripts("Сервисные"))

    def test_needs_alphabet_rewrite_after_normalization(self) -> None:
        self.assertFalse(
            needs_alphabet_rewrite("Сервicenые стандарты", "ru")
        )


class LanguageGuardMixedAlphabetIntegrationTests(unittest.TestCase):
    def test_mixed_homoglyph_word_becomes_script_pure_without_rewrite(self) -> None:
        answer = "Проверьте контрol качества перед открытием смены."
        self.assertFalse(needs_language_rewrite(answer, "ru"))

    def test_unfixable_mixed_word_triggers_rewrite(self) -> None:
        answer = "Серв1cenые стандарты обслуживания."
        self.assertTrue(needs_language_rewrite(answer, "ru"))


if __name__ == "__main__":
    unittest.main()
