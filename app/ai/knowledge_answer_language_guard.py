"""Language compliance guard for grounded Knowledge Base answers.

Detects obvious cross-language leakage in AI-generated answers and performs
at most one rewrite call to enforce the requested response language.
"""

from __future__ import annotations

import re
from typing import Tuple

from app.ai.client import AIClient
from app.ai.knowledge_answer_interfaces import KnowledgeAnswerResult
from app.ai.knowledge_answer_alphabet_guard import (
    has_unfixable_mixed_alphabet,
    normalize_answer_alphabet,
)
from app.ai.review_language import (
    KAZAKH_SPECIFIC_LETTERS,
    SUPPORTED_REVIEW_LANGUAGES,
    normalize_review_language,
)

_LANGUAGE_LABELS = {
    "ru": "Russian",
    "kk": "Kazakh",
    "en": "English",
}

# Cyrillic letters that strongly suggest Russian rather than Kazakh.
# ``ы`` is shared and is only treated as Russian when the whole answer lacks
# Kazakh-specific letters.
_RUSSIAN_INDICATOR_LETTERS = frozenset("ыэщъёЫЭЩЪЁ")
_STRONG_RUSSIAN_INDICATOR_LETTERS = frozenset("эщъёЭЩЪЁ")

# High-confidence Russian adverb/adjective suffixes (not domain-specific).
_RUSSIAN_LEAKAGE_SUFFIXES = (
    "иво",
    "ово",
    "енно",
    "ески",
    "ично",
)

# High-confidence Russian function words (grammatical, not domain-specific).
_RUSSIAN_FUNCTION_WORDS = frozenset(
    {
        "и",
        "в",
        "во",
        "на",
        "не",
        "но",
        "что",
        "как",
        "это",
        "для",
        "при",
        "или",
        "от",
        "по",
        "за",
        "из",
        "у",
        "о",
        "об",
        "до",
        "без",
        "же",
        "ли",
        "бы",
        "уже",
        "ещё",
        "еще",
        "все",
        "этот",
        "тот",
        "так",
        "где",
        "когда",
        "если",
        "чтобы",
        "после",
        "между",
        "через",
        "над",
        "под",
        "там",
        "здесь",
        "тоже",
        "только",
        "можно",
        "нужно",
        "должен",
        "должна",
        "должны",
        "необходимо",
    }
)


class KnowledgeAnswerLanguageRewriteError(Exception):
    """Raised when a language-compliance rewrite fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


_WORD_PATTERN = re.compile(
    r"[A-Za-z"
    r"А-Яа-яЁё"
    r"ӘәІіҢңҒғҮүҰұҚқӨөҺһ"
    r"']+",
    re.UNICODE,
)

# Quoted spans such as «спрашивай», "этап", or 'раздел'.
_QUOTED_SEGMENT_PATTERN = re.compile(
    r"[«\"']([^«»\"']+)[»\"']",
    re.UNICODE,
)


def _extract_words(text: str) -> Tuple[str, ...]:
    return tuple(match.group(0) for match in _WORD_PATTERN.finditer(text))


def _contains_kazakh_specific_letters(text: str) -> bool:
    return any(character in KAZAKH_SPECIFIC_LETTERS for character in text)


def _word_has_kazakh_specific_letters(word: str) -> bool:
    return any(character in KAZAKH_SPECIFIC_LETTERS for character in word)


def _word_has_russian_indicator_letters(word: str) -> bool:
    return any(character in _RUSSIAN_INDICATOR_LETTERS for character in word)


def _word_has_strong_russian_indicator_letters(word: str) -> bool:
    return any(character in _STRONG_RUSSIAN_INDICATOR_LETTERS for character in word)


def _is_latin_word(word: str) -> bool:
    letters = [character for character in word if character.isalpha()]
    if not letters:
        return False
    return all(ord(character) < 128 for character in letters)


def _is_cyrillic_word(word: str) -> bool:
    letters = [character for character in word if character.isalpha()]
    if not letters:
        return False
    return all("\u0400" <= character <= "\u04FF" for character in letters)


def _alpha_length(word: str) -> int:
    return len("".join(character for character in word if character.isalpha()))


def _normalized_word_key(word: str) -> str:
    return "".join(character for character in word if character.isalpha()).lower()


def _is_likely_proper_noun(word: str) -> bool:
    """Return True when *word* is likely an acronym or proper noun."""
    alpha = "".join(character for character in word if character.isalpha())
    if not alpha:
        return True
    if len(alpha) <= 2:
        return True
    if alpha.isupper():
        return True
    return False


def _meaningful_latin_words(words: Tuple[str, ...]) -> Tuple[str, ...]:
    meaningful: list[str] = []
    for word in words:
        if not _is_latin_word(word):
            continue
        if _alpha_length(word) < 3:
            continue
        if _is_likely_proper_noun(word):
            continue
        meaningful.append(word)
    return tuple(meaningful)


def _meaningful_cyrillic_words(words: Tuple[str, ...]) -> Tuple[str, ...]:
    meaningful: list[str] = []
    for word in words:
        if not _is_cyrillic_word(word):
            continue
        if _alpha_length(word) < 3:
            continue
        if _is_likely_proper_noun(word):
            continue
        meaningful.append(word)
    return tuple(meaningful)


def _detect_latin_leakage(
    latin_words: Tuple[str, ...],
    cyrillic_words: Tuple[str, ...],
) -> bool:
    if len(latin_words) >= 2:
        return True
    if len(latin_words) == 1:
        if len(cyrillic_words) >= 3:
            return False
        if _alpha_length(latin_words[0]) >= 5:
            return True
    return False


def _detect_english_violation(answer: str) -> bool:
    words = _extract_words(answer)
    cyrillic_words = _meaningful_cyrillic_words(words)
    # Any meaningful Cyrillic token in an English answer is cross-language leakage.
    return bool(cyrillic_words)


def _detect_russian_violation(answer: str) -> bool:
    words = _extract_words(answer)
    if _contains_kazakh_specific_letters(answer):
        return True

    latin_words = _meaningful_latin_words(words)
    cyrillic_words = _meaningful_cyrillic_words(words)
    return _detect_latin_leakage(latin_words, cyrillic_words)


def _russian_only_cyrillic_word(word: str) -> bool:
    return _is_cyrillic_word(word) and not _word_has_kazakh_specific_letters(word)


def _is_russian_function_word(word: str) -> bool:
    return _normalized_word_key(word) in _RUSSIAN_FUNCTION_WORDS


def _is_high_confidence_russian_leakage_word(word: str) -> bool:
    """Return True when *word* is very likely ordinary Russian, not shared Cyrillic."""
    if _is_russian_function_word(word):
        return True
    if _word_has_strong_russian_indicator_letters(word):
        return True

    key = _normalized_word_key(word)
    if len(key) < 4:
        return False
    if any(key.endswith(suffix) for suffix in _RUSSIAN_LEAKAGE_SUFFIXES):
        return True
    if key.endswith(("тся", "ться")):
        return True
    return False


def _run_indicates_russian_leakage(run: Tuple[str, ...]) -> bool:
    if len(run) < 2:
        return False

    if any(_is_high_confidence_russian_leakage_word(word) for word in run):
        return True

    function_words = sum(1 for word in run if _is_russian_function_word(word))
    if function_words >= 2:
        return True

    return False


def _find_longest_russian_only_run(words: Tuple[str, ...]) -> Tuple[str, ...]:
    longest: Tuple[str, ...] = ()
    current: list[str] = []

    for word in words:
        if _russian_only_cyrillic_word(word):
            current.append(word)
            continue

        if len(current) > len(longest):
            longest = tuple(current)
        current = []

    if len(current) > len(longest):
        longest = tuple(current)

    return longest


def _extract_quoted_segments(text: str) -> Tuple[str, ...]:
    return tuple(
        match.group(1).strip()
        for match in _QUOTED_SEGMENT_PATTERN.finditer(text)
        if match.group(1).strip()
    )


def _segment_has_russian_only_leakage(segment: str) -> bool:
    """Return True when *segment* contains meaningful Russian-only Cyrillic."""
    words = _meaningful_cyrillic_words(_extract_words(segment))
    russian_only_words = tuple(
        word for word in words if _russian_only_cyrillic_word(word)
    )
    if not russian_only_words:
        return False

    if any(_is_high_confidence_russian_leakage_word(word) for word in russian_only_words):
        return True

    # Quoted spans often preserve untranslated Russian source terminology.
    if any(_alpha_length(word) >= 5 for word in russian_only_words):
        return True

    return False


def _detect_quoted_russian_leakage_in_kazakh(answer: str) -> bool:
    """Detect Russian terminology inside quotes within an otherwise Kazakh answer."""
    if not _contains_kazakh_specific_letters(answer):
        return False
    return any(
        _segment_has_russian_only_leakage(segment)
        for segment in _extract_quoted_segments(answer)
    )


def _detect_isolated_russian_token_in_kazakh(
    answer: str,
    cyrillic_words: Tuple[str, ...],
) -> bool:
    """Detect a substantial Russian-only token inside an otherwise Kazakh answer."""
    if not _contains_kazakh_specific_letters(answer):
        return False

    for word in cyrillic_words:
        if not _russian_only_cyrillic_word(word):
            continue
        if _is_likely_proper_noun(word):
            continue
        if _is_high_confidence_russian_leakage_word(word):
            return True
    return False


def _detect_kazakh_violation(answer: str) -> bool:
    words = _extract_words(answer)
    latin_words = _meaningful_latin_words(words)
    cyrillic_words = _meaningful_cyrillic_words(words)

    if _detect_latin_leakage(latin_words, cyrillic_words):
        return True

    if _detect_quoted_russian_leakage_in_kazakh(answer):
        return True

    if _detect_isolated_russian_token_in_kazakh(answer, cyrillic_words):
        return True

    if not cyrillic_words:
        return False

    longest_russian_only_run = _find_longest_russian_only_run(cyrillic_words)
    if _run_indicates_russian_leakage(longest_russian_only_run):
        return True

    if any(
        _word_has_strong_russian_indicator_letters(word)
        and not _word_has_kazakh_specific_letters(word)
        for word in cyrillic_words
    ):
        return True

    if not _contains_kazakh_specific_letters(answer):
        if any(_word_has_russian_indicator_letters(word) for word in cyrillic_words):
            return True
        if len(cyrillic_words) >= 3:
            return True

    return False


def needs_language_rewrite(answer: str, requested_language: str) -> bool:
    """Return True when *answer* clearly violates *requested_language*."""
    language = normalize_review_language(requested_language)
    if language is None:
        return False

    normalized = answer.strip()
    if not normalized:
        return False

    if has_unfixable_mixed_alphabet(normalized, language):
        return True

    if language == "en":
        return _detect_english_violation(normalized)
    if language == "ru":
        return _detect_russian_violation(normalized)
    if language == "kk":
        return _detect_kazakh_violation(normalized)
    return False


def _language_specific_rewrite_rules(language: str) -> Tuple[str, ...]:
    """Return additional rewrite instructions for *language*."""
    if language == "kk":
        return (
            "- Write the entire answer in natural Kazakh.",
            (
                "- Do not leave ordinary Russian words, Russian adverbs, "
                "Russian workflow terms, Russian business terminology, or "
                "Russian explanatory phrases in the answer."
            ),
            (
                "- Examples of unacceptable leakage when they are ordinary "
                "business or process terms: ненавязчиво, спрашивай, благодари, "
                "возврат, оформление."
            ),
            (
                "- Translate such terms into natural Kazakh equivalents. "
                "Do not copy Russian text from source documents merely because "
                "it appears in the source."
            ),
            (
                "- Preserve only genuine proper nouns such as company names, "
                "brand names, trademarks, product names, filenames, and "
                "document titles."
            ),
            (
                "- Before returning, internally review the rewritten answer "
                "and remove any remaining ordinary Russian or English words."
            ),
        )
    return ()


def build_language_rewrite_prompt(answer: str, requested_language: str) -> str:
    """Build a deterministic rewrite prompt for language compliance."""
    language = normalize_review_language(requested_language)
    if language is None or language not in SUPPORTED_REVIEW_LANGUAGES:
        raise ValueError("Unsupported response language.")

    label = _LANGUAGE_LABELS[language]
    lines = [
        "Rewrite the following corporate Knowledge Base answer for language compliance.",
        "",
        "Rules:",
        f"- Write ONLY in {label} (language code: {language}).",
        "- Preserve every factual claim and meaning exactly.",
        "- Do not add, remove, infer, or change facts.",
        (
            "- Translate ordinary business terminology, headings, workflow "
            "stage names, process names, rules, instructions, and employee "
            f"actions into {label}."
        ),
        (
            "- Only genuine proper nouns may remain in another language: "
            "company names, brand names, trademarks, product names, "
            "filenames, and document titles."
        ),
        "- Return ONLY the rewritten answer text.",
        "- Do not return JSON, Markdown, code fences, or commentary.",
        (
            "- Do not mix Latin and Cyrillic letters inside the same word. "
            "Use one consistent alphabet per word."
        ),
    ]
    lines.extend(_language_specific_rewrite_rules(language))
    lines.extend(
        [
            "",
            "Answer to rewrite:",
            answer.strip(),
        ]
    )
    return "\n".join(lines).rstrip("\n")


class KnowledgeAnswerLanguageGuard:
    """Enforce response-language compliance with at most one rewrite."""

    def __init__(self, provider: AIClient) -> None:
        self._provider = provider

    def enforce(
        self,
        result: KnowledgeAnswerResult,
        requested_language: str,
    ) -> KnowledgeAnswerResult:
        """Return *result* or a language-compliant copy with rewritten answer."""
        normalized_answer = normalize_answer_alphabet(
            result.answer,
            requested_language,
        )
        if not needs_language_rewrite(normalized_answer, requested_language):
            if normalized_answer == result.answer:
                return result
            return KnowledgeAnswerResult(
                answer=normalized_answer,
                citations=result.citations,
                sufficient_context=result.sufficient_context,
            )

        working = KnowledgeAnswerResult(
            answer=normalized_answer,
            citations=result.citations,
            sufficient_context=result.sufficient_context,
        )

        prompt = build_language_rewrite_prompt(working.answer, requested_language)
        try:
            rewritten = self._provider.generate(prompt)
        except Exception as exc:
            raise KnowledgeAnswerLanguageRewriteError(
                "Failed to rewrite knowledge answer for language compliance."
            ) from exc

        normalized = normalize_answer_alphabet(
            rewritten.strip(),
            requested_language,
        )
        if not normalized:
            raise KnowledgeAnswerLanguageRewriteError(
                "Failed to rewrite knowledge answer for language compliance."
            )

        if has_unfixable_mixed_alphabet(normalized, requested_language):
            raise KnowledgeAnswerLanguageRewriteError(
                "Failed to rewrite knowledge answer for language compliance."
            )

        if needs_language_rewrite(normalized, requested_language):
            raise KnowledgeAnswerLanguageRewriteError(
                "Failed to rewrite knowledge answer for language compliance."
            )

        return KnowledgeAnswerResult(
            answer=normalized,
            citations=result.citations,
            sufficient_context=result.sufficient_context,
        )
