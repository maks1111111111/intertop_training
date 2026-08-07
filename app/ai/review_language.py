"""Language resolution for AI practical-task review."""

from __future__ import annotations

from typing import Optional

SUPPORTED_REVIEW_LANGUAGES = frozenset({"en", "kk", "ru"})

_KAZAKH_SPECIFIC_LETTERS = frozenset("әіңғүұқөһӘІҢҒҮҰҚӨҮ")


def normalize_review_language(raw: str) -> Optional[str]:
    """Return a supported language code, or ``None`` if *raw* is invalid."""
    if not isinstance(raw, str):
        return None

    normalized = raw.strip().lower()
    if normalized in SUPPORTED_REVIEW_LANGUAGES:
        return normalized

    return None


def _detect_language_from_text(*texts: str) -> Optional[str]:
    combined = "\n".join(text for text in texts if text)
    if not combined.strip():
        return None

    if any(character in _KAZAKH_SPECIFIC_LETTERS for character in combined):
        return "kk"

    if any("\u0400" <= character <= "\u04FF" for character in combined):
        return "ru"

    if any(character.isalpha() and ord(character) < 128 for character in combined):
        return "en"

    return None


def resolve_review_language(course_language: str, *task_texts: str) -> str:
    """Resolve the response language for practical-task review.

    Priority:

    1. Valid course language code.
    2. Heuristic detection from task text (not the learner answer).
    3. Russian default.
    """
    normalized_course = normalize_review_language(course_language)
    if normalized_course is not None:
        return normalized_course

    detected = _detect_language_from_text(*task_texts)
    if detected is not None:
        return detected

    return "ru"
