"""Shared models for admin lesson question preview editing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminLessonQuestionEditInput:
    index: int
    text: str
    option_texts: tuple[tuple[str, str], ...]
    correct_option_id: str
    explanation: str
