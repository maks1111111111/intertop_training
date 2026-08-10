"""Tests for knowledge text chunking."""

from __future__ import annotations

import unittest

from app.knowledge.chunking import (
    DEFAULT_MIN_CHUNK_CHARS,
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    KnowledgeChunk,
    KnowledgeChunkingOptions,
    KnowledgeTextChunker,
)


class KnowledgeTextChunkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunker = KnowledgeTextChunker()

    def test_empty_string_returns_empty_tuple(self) -> None:
        self.assertEqual(self.chunker.chunk(""), ())

    def test_whitespace_only_returns_empty_tuple(self) -> None:
        self.assertEqual(self.chunker.chunk("   \n\t  \r\n  "), ())

    def test_one_short_paragraph_produces_one_chunk(self) -> None:
        text = "Короткий абзац знаний."
        chunks = self.chunker.chunk(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, text)
        self.assertEqual(chunks[0].index, 0)
        self.assertEqual(chunks[0].start_char, 0)
        self.assertEqual(chunks[0].end_char, len(text))

    def test_multiple_short_paragraphs(self) -> None:
        text = "Первый абзац.\n\nВторой абзац.\n\nТретий абзац."
        options = KnowledgeChunkingOptions(
            target_chars=40,
            overlap_chars=5,
            min_chunk_chars=5,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreaterEqual(len(chunks), 2)
        combined = "".join(chunk.text for chunk in chunks)
        self.assertIn("Первый", combined)
        self.assertIn("Третий", combined)

    def test_paragraph_boundary_preferred(self) -> None:
        paragraph_a = "A" * 80
        paragraph_b = "B" * 80
        text = f"{paragraph_a}\n\n{paragraph_b}"
        options = KnowledgeChunkingOptions(
            target_chars=100,
            overlap_chars=10,
            min_chunk_chars=20,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(chunks[0].text.endswith("\n\n") or paragraph_a in chunks[0].text)

    def test_sentence_boundary_preferred_when_paragraph_too_long(self) -> None:
        sentence_a = "Первое предложение длинное." + (" x" * 30)
        sentence_b = "Второе предложение тоже длинное." + (" y" * 30)
        text = f"{sentence_a} {sentence_b}"
        options = KnowledgeChunkingOptions(
            target_chars=120,
            overlap_chars=10,
            min_chunk_chars=20,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn(".", chunks[0].text)

    def test_whitespace_boundary_fallback(self) -> None:
        words = ["word"] * 40
        text = " ".join(words)
        options = KnowledgeChunkingOptions(
            target_chars=60,
            overlap_chars=5,
            min_chunk_chars=10,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertTrue(chunk.text.strip())

    def test_hard_split_for_extremely_long_token_like_text(self) -> None:
        text = "x" * 250
        options = KnowledgeChunkingOptions(
            target_chars=100,
            overlap_chars=10,
            min_chunk_chars=20,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(len(chunks[0].text), options.target_chars)

    def test_long_russian_text(self) -> None:
        paragraph = (
            "Компания обязана соблюдать стандарты обслуживания клиентов. "
            "Сотрудник должен приветствовать посетителя и предложить помощь. "
            "При возврате товара необходимо проверить чек и состояние изделия."
        )
        text = "\n\n".join([paragraph] * 8)
        chunks = self.chunker.chunk(
            text,
            KnowledgeChunkingOptions(
                target_chars=180,
                overlap_chars=20,
                min_chunk_chars=40,
            ),
        )
        self.assertGreater(len(chunks), 1)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        for chunk in chunks:
            self.assertEqual(chunk.text, normalized[chunk.start_char : chunk.end_char])
            self.assertTrue(chunk.text.strip())

    def test_unicode_and_kazakh_characters_preserved(self) -> None:
        text = "Қазақ тілі мәтіні.\n\nEnglish text.\n\nРусский текст."
        chunks = self.chunker.chunk(
            text,
            KnowledgeChunkingOptions(
                target_chars=30,
                overlap_chars=5,
                min_chunk_chars=5,
            ),
        )
        self.assertGreaterEqual(len(chunks), 1)
        joined = "".join(chunk.text for chunk in chunks)
        self.assertIn("Қазақ", joined)
        self.assertIn("English", joined)
        self.assertIn("Русский", joined)

    def test_deterministic_repeated_calls(self) -> None:
        text = "Deterministic chunking test.\n\n" * 20
        options = KnowledgeChunkingOptions(
            target_chars=80,
            overlap_chars=10,
            min_chunk_chars=15,
        )
        first = self.chunker.chunk(text, options)
        second = self.chunker.chunk(text, options)
        self.assertEqual(first, second)

    def test_stable_increasing_indexes(self) -> None:
        text = "Index test. " * 50
        options = KnowledgeChunkingOptions(
            target_chars=60,
            overlap_chars=5,
            min_chunk_chars=10,
        )
        chunks = self.chunker.chunk(text, options)
        indexes = [chunk.index for chunk in chunks]
        self.assertEqual(indexes, list(range(len(chunks))))

    def test_valid_start_and_end_offsets(self) -> None:
        text = "Offset validation.\n\n" * 15
        options = KnowledgeChunkingOptions(
            target_chars=50,
            overlap_chars=8,
            min_chunk_chars=10,
        )
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks = self.chunker.chunk(text, options)
        for chunk in chunks:
            self.assertGreaterEqual(chunk.start_char, 0)
            self.assertLess(chunk.start_char, chunk.end_char)
            self.assertEqual(chunk.text, normalized[chunk.start_char : chunk.end_char])

    def test_no_empty_chunks(self) -> None:
        text = "No empty chunks.\n\nAnother paragraph.\n\nFinal paragraph."
        options = KnowledgeChunkingOptions(
            target_chars=35,
            overlap_chars=5,
            min_chunk_chars=5,
        )
        chunks = self.chunker.chunk(text, options)
        for chunk in chunks:
            self.assertTrue(chunk.text.strip())

    def test_overlap_appears_between_adjacent_chunks(self) -> None:
        text = "Overlap test sentence. " * 30
        options = KnowledgeChunkingOptions(
            target_chars=80,
            overlap_chars=20,
            min_chunk_chars=20,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreaterEqual(len(chunks), 2)
        first_tail = chunks[0].text[-20:]
        second_head = chunks[1].text[:20]
        self.assertEqual(first_tail, second_head)

    def test_overlap_smaller_than_target_size(self) -> None:
        options = KnowledgeChunkingOptions(
            target_chars=100,
            overlap_chars=25,
            min_chunk_chars=20,
        )
        self.assertLess(options.overlap_chars, options.target_chars)

    def test_overlap_cannot_cause_infinite_loop(self) -> None:
        parts = [f"Section {index:03d} with unique content. " for index in range(100)]
        text = "".join(parts)
        options = KnowledgeChunkingOptions(
            target_chars=70,
            overlap_chars=69,
            min_chunk_chars=10,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreater(len(chunks), 1)
        self.assertLess(len(chunks), 1000)
        indexes = [chunk.index for chunk in chunks]
        self.assertEqual(indexes, list(range(len(chunks))))
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        previous_start = -1
        for chunk in chunks:
            self.assertEqual(chunk.text, normalized[chunk.start_char : chunk.end_char])
            self.assertGreater(chunk.start_char, previous_start)
            previous_start = chunk.start_char

    def test_legitimate_repeated_text_not_discarded(self) -> None:
        paragraph = "Identical policy paragraph for all regions.\n\n"
        text = paragraph * 5
        options = KnowledgeChunkingOptions(
            target_chars=60,
            overlap_chars=10,
            min_chunk_chars=10,
        )
        chunks = self.chunker.chunk(text, options)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        last_paragraph_start = len(paragraph) * 4
        self.assertTrue(
            any(
                chunk.start_char <= last_paragraph_start < chunk.end_char
                for chunk in chunks
            )
        )
        text_to_starts: dict[str, list[int]] = {}
        for chunk in chunks:
            text_to_starts.setdefault(chunk.text, []).append(chunk.start_char)
        duplicate_texts = [
            starts for starts in text_to_starts.values() if len(starts) > 1
        ]
        if duplicate_texts:
            for starts in duplicate_texts:
                self.assertEqual(len(starts), len(set(starts)))

    def test_complete_source_coverage(self) -> None:
        paragraphs = [
            "Политика возврата товара в розничной сети.",
            "Сотрудник обязан проверить чек и состояние изделия.",
            "Клиент получает ответ в течение рабочего дня.",
            "Критичные нарушения эскалируются руководителю смены.",
            "Документ актуален для всех магазинов сети.",
        ]
        text = "\n\n".join(paragraphs * 12)
        options = KnowledgeChunkingOptions(
            target_chars=120,
            overlap_chars=25,
            min_chunk_chars=30,
        )
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks = self.chunker.chunk(text, options)
        covered = [False] * len(normalized)
        for chunk in chunks:
            for index in range(chunk.start_char, chunk.end_char):
                covered[index] = True
        for index, character in enumerate(normalized):
            if not character.isspace():
                self.assertTrue(
                    covered[index],
                    f"Position {index} not covered: {character!r}",
                )

    def test_repeated_content_document_terminates(self) -> None:
        unit = "Repeated section content. " * 5
        text = unit * 50
        options = KnowledgeChunkingOptions(
            target_chars=100,
            overlap_chars=30,
            min_chunk_chars=20,
        )
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks = self.chunker.chunk(text, options)
        self.assertGreater(len(chunks), 1)
        self.assertLess(len(chunks), len(normalized))
        for chunk in chunks:
            self.assertEqual(chunk.text, normalized[chunk.start_char : chunk.end_char])
            self.assertTrue(chunk.text.strip())
        last_content_index = len(normalized) - 1
        while last_content_index >= 0 and normalized[last_content_index].isspace():
            last_content_index -= 1
        self.assertTrue(
            any(
                chunk.start_char <= last_content_index < chunk.end_char
                for chunk in chunks
            )
        )

    def test_tiny_trailing_section_handled_sensibly(self) -> None:
        main = "M" * 90
        tiny = "Tiny."
        text = f"{main}\n\n{tiny}"
        options = KnowledgeChunkingOptions(
            target_chars=100,
            overlap_chars=5,
            min_chunk_chars=20,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Tiny.", chunks[0].text)

    def test_invalid_target_chars_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.chunker.chunk(
                "text",
                KnowledgeChunkingOptions(target_chars=0),
            )

    def test_invalid_overlap_chars_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.chunker.chunk(
                "text",
                KnowledgeChunkingOptions(overlap_chars=-1),
            )

    def test_overlap_greater_or_equal_target_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.chunker.chunk(
                "text",
                KnowledgeChunkingOptions(target_chars=50, overlap_chars=50),
            )
        with self.assertRaises(ValueError):
            self.chunker.chunk(
                "text",
                KnowledgeChunkingOptions(target_chars=50, overlap_chars=60),
            )

    def test_invalid_min_chunk_chars_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.chunker.chunk(
                "text",
                KnowledgeChunkingOptions(min_chunk_chars=0),
            )

    def test_min_chunk_chars_greater_than_target_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.chunker.chunk(
                "text",
                KnowledgeChunkingOptions(target_chars=50, min_chunk_chars=51),
            )

    def test_custom_options_work(self) -> None:
        text = "Custom options. " * 20
        options = KnowledgeChunkingOptions(
            target_chars=55,
            overlap_chars=7,
            min_chunk_chars=12,
        )
        chunks = self.chunker.chunk(text, options)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertLessEqual(len(chunks[0].text), options.target_chars)

    def test_source_input_not_mutated(self) -> None:
        original = "Original\r\nLine endings.\n\nSecond paragraph."
        snapshot = original
        self.chunker.chunk(original)
        self.assertEqual(original, snapshot)

    def test_line_endings_normalized(self) -> None:
        text = "First\r\nSecond\r\n\r\nThird"
        chunks = self.chunker.chunk(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "First\nSecond\n\nThird")
        self.assertNotIn("\r", chunks[0].text)

    def test_default_options_constants(self) -> None:
        self.assertEqual(DEFAULT_TARGET_CHARS, 1200)
        self.assertEqual(DEFAULT_OVERLAP_CHARS, 150)
        self.assertEqual(DEFAULT_MIN_CHUNK_CHARS, 100)

    def test_default_options_used_when_none(self) -> None:
        text = "Short."
        chunks = self.chunker.chunk(text)
        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(chunks[0], KnowledgeChunk)


if __name__ == "__main__":
    unittest.main()
