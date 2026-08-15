"""Output language instructions for AI course and quiz generation."""

from __future__ import annotations

from typing import Optional

from app.ai.review_language import normalize_review_language

_LANGUAGE_LABELS = {
    "ru": "Russian",
    "kk": "Kazakh",
    "en": "English",
}


def normalize_output_language(raw: Optional[str]) -> Optional[str]:
    """Return a supported output language code, or ``None`` if unset/invalid."""
    if raw is None:
        return None
    return normalize_review_language(str(raw))


def build_generation_language_instruction_lines(language: str) -> list[str]:
    """Build deterministic prompt lines requiring a specific output language."""
    label = _LANGUAGE_LABELS.get(language, language)
    lines = [
        "Output language (mandatory):",
        f'- Language code: "{language}"',
        f"- Write ALL human-readable generated text only in {label}.",
        "- The selected output language is authoritative.",
        (
            "- The language of the source material MUST NOT determine the "
            "output language."
        ),
        (
            "- English JSON field names and schema examples do NOT mean "
            "content should be written in English."
        ),
        (
            "- Translate supported information from the source material into "
            f"{label} when necessary."
        ),
        (
            "- Use the output language consistently for every human-readable "
            "string in the response."
        ),
        (
            "- This includes course title and description; every lesson title, "
            "summary, and content; learning objectives; practical task title, "
            "description, and expected result; checklist items; common "
            "mistakes; key takeaways; application tips; quiz title; question "
            "text; answer option text; and explanations."
        ),
        (
            "- Translate ordinary business terminology into the output "
            "language, including section headings, workflow stage names, "
            "process step names, instructions, rules, and employee actions."
        ),
        (
            "- Do not preserve source-language workflow labels merely because "
            "they appear in the source document."
        ),
        (
            "- Only genuine proper nouns may remain in their original "
            "language when appropriate: company names, brand names, "
            "trademarks, product names, filenames, and document titles."
        ),
    ]

    if language == "en":
        lines.append(
            "- Do not write generated content in Russian or Kazakh, even when "
            "the source material is in those languages."
        )
    elif language == "kk":
        lines.append(
            "- Do not write generated content in Russian or English, even when "
            "the source material is in those languages."
        )
    elif language == "ru":
        lines.append(
            "- Do not write generated content in Kazakh or English, even when "
            "the source material is in those languages."
        )

    return lines
