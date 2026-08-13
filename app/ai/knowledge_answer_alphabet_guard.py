"""Mixed-script detection and homoglyph normalization for Knowledge Base answers.

For Russian and Kazakh responses, Latin and Cyrillic must not appear together
inside the same word. Obvious homoglyph confusables are normalized deterministically
before optional language-compliance rewriting.
"""

from __future__ import annotations

import re
from typing import Tuple

from app.ai.review_language import normalize_review_language

# Latin letters that visually match Cyrillic counterparts.
_HOMOGLYPH_LATIN_TO_CYRILLIC = str.maketrans(
    {
        "A": "А",
        "a": "а",
        "B": "В",
        "C": "С",
        "c": "с",
        "E": "Е",
        "e": "е",
        "H": "Н",
        "h": "н",
        "I": "И",
        "i": "и",
        "K": "К",
        "k": "к",
        "M": "М",
        "m": "м",
        "O": "О",
        "o": "о",
        "P": "Р",
        "p": "р",
        "T": "Т",
        "t": "т",
        "X": "Х",
        "x": "х",
        "Y": "У",
        "y": "у",
        "N": "Н",
        "n": "н",
        "L": "Л",
        "l": "л",
        "D": "Д",
        "d": "д",
    }
)

_WORD_PATTERN = re.compile(
    r"[A-Za-z"
    r"А-Яа-яЁё"
    r"ӘәІіҢңҒғҮүҰұҚқӨөҺһ"
    r"']+",
    re.UNICODE,
)


def _is_latin_letter(character: str) -> bool:
    return character.isalpha() and ord(character) < 128


def _is_cyrillic_letter(character: str) -> bool:
    return character.isalpha() and "\u0400" <= character <= "\u04FF"


def _word_script_counts(word: str) -> Tuple[int, int]:
    latin = 0
    cyrillic = 0
    for character in word:
        if _is_latin_letter(character):
            latin += 1
        elif _is_cyrillic_letter(character):
            cyrillic += 1
    return latin, cyrillic


def word_has_mixed_scripts(word: str) -> bool:
    """Return True when *word* contains both Latin and Cyrillic letters."""
    latin, cyrillic = _word_script_counts(word)
    return latin > 0 and cyrillic > 0


def normalize_word_homoglyphs(word: str) -> str:
    """Replace obvious Latin homoglyphs when Cyrillic dominates the word."""
    latin, cyrillic = _word_script_counts(word)
    if latin == 0 or cyrillic == 0:
        return word
    if cyrillic >= latin:
        return word.translate(_HOMOGLYPH_LATIN_TO_CYRILLIC)
    return word


def normalize_answer_alphabet(answer: str, language: str) -> str:
    """Normalize homoglyphs word-by-word for Cyrillic response languages."""
    normalized_language = normalize_review_language(language)
    if normalized_language not in {"ru", "kk"}:
        return answer

    def replace_word(match: re.Match[str]) -> str:
        return normalize_word_homoglyphs(match.group(0))

    return _WORD_PATTERN.sub(replace_word, answer)


def has_unfixable_mixed_alphabet(answer: str, language: str) -> bool:
    """Return True when Cyrillic answers still contain mixed-script words."""
    normalized_language = normalize_review_language(language)
    if normalized_language not in {"ru", "kk"}:
        return False

    normalized = normalize_answer_alphabet(answer, language)
    for match in _WORD_PATTERN.finditer(normalized):
        if word_has_mixed_scripts(match.group(0)):
            return True
    return False


def needs_alphabet_rewrite(answer: str, language: str) -> bool:
    """Return True when mixed-script words remain after homoglyph normalization."""
    return has_unfixable_mixed_alphabet(answer, language)
