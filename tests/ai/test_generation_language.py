"""Tests for AI generation output language helpers."""

from __future__ import annotations

import unittest

from app.ai.generation_language import (
    build_generation_language_instruction_lines,
    normalize_output_language,
)


class GenerationLanguageTests(unittest.TestCase):
    """Tests for generation output language normalization and prompts."""

    def test_normalize_output_language_accepts_ru_kk_en(self) -> None:
        self.assertEqual(normalize_output_language("ru"), "ru")
        self.assertEqual(normalize_output_language("KK"), "kk")
        self.assertEqual(normalize_output_language(" en "), "en")

    def test_normalize_output_language_rejects_invalid(self) -> None:
        self.assertIsNone(normalize_output_language("auto"))
        self.assertIsNone(normalize_output_language("fr"))
        self.assertIsNone(normalize_output_language(None))

    def test_ru_instruction_requires_russian_content(self) -> None:
        lines = build_generation_language_instruction_lines("ru")

        self.assertIn('Language code: "ru"', "\n".join(lines))
        self.assertIn("only in Russian", "\n".join(lines))
        self.assertIn("source material MUST NOT determine the output language", "\n".join(lines))
        self.assertIn("course title and description", "\n".join(lines))
        self.assertIn("Do not write generated content in Kazakh or English", "\n".join(lines))

    def test_kk_instruction_requires_kazakh_content(self) -> None:
        lines = build_generation_language_instruction_lines("kk")

        self.assertIn('Language code: "kk"', "\n".join(lines))
        self.assertIn("only in Kazakh", "\n".join(lines))
        self.assertIn("Do not write generated content in Russian or English", "\n".join(lines))

    def test_en_instruction_requires_english_content(self) -> None:
        lines = build_generation_language_instruction_lines("en")

        self.assertIn('Language code: "en"', "\n".join(lines))
        self.assertIn("only in English", "\n".join(lines))
        self.assertIn("Do not write generated content in Russian or Kazakh", "\n".join(lines))

    def test_instruction_covers_quiz_fields(self) -> None:
        lines = "\n".join(build_generation_language_instruction_lines("ru"))

        self.assertIn("quiz title", lines)
        self.assertIn("question text", lines)
        self.assertIn("answer option text", lines)
        self.assertIn("explanations", lines)


if __name__ == "__main__":
    unittest.main()
