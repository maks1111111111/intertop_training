"""In-memory store for AI-generated lesson question previews."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional, Tuple

_PREVIEW_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class StoredPreviewQuestion:
    """Structured preview question payload safe for later quiz persistence."""

    text: str
    question_type: str
    options: Tuple[Tuple[str, str], ...]
    correct_option_ids: Tuple[str, ...]
    explanation: str
    difficulty: int
    tags: Tuple[str, ...]
    ai_context: str = ""


@dataclass
class LessonQuestionPreviewRecord:
    """Server-side preview session bound to one course lesson."""

    preview_id: str
    slug: str
    lesson_id: str
    questions: Tuple[StoredPreviewQuestion, ...]
    consumed: bool = False


class AdminLessonQuestionPreviewStoreError(Exception):
    """Raised when preview store access is invalid."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AdminLessonQuestionPreviewStore:
    """Single-process in-memory preview store for AI lesson question previews."""

    def __init__(self) -> None:
        self._records: dict[str, LessonQuestionPreviewRecord] = {}

    def save(
        self,
        slug: str,
        lesson_id: str,
        questions: Tuple[StoredPreviewQuestion, ...],
    ) -> str:
        """Persist a generated preview and return its opaque identifier."""
        preview_id = uuid.uuid4().hex
        self._records[preview_id] = LessonQuestionPreviewRecord(
            preview_id=preview_id,
            slug=slug,
            lesson_id=lesson_id,
            questions=questions,
        )
        return preview_id

    def get(self, preview_id: str) -> Optional[LessonQuestionPreviewRecord]:
        """Return an active preview record, or ``None`` if missing or consumed."""
        normalized = _validate_preview_id(preview_id)
        record = self._records.get(normalized)
        if record is None or record.consumed:
            return None
        return record

    def consume(self, preview_id: str) -> Optional[LessonQuestionPreviewRecord]:
        """Mark a preview as consumed so it cannot be applied again."""
        record = self.get(preview_id)
        if record is None:
            return None
        record.consumed = True
        return record


def _validate_preview_id(raw: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized or not _PREVIEW_ID_PATTERN.match(normalized):
        raise AdminLessonQuestionPreviewStoreError(
            "Предпросмотр вопросов недоступен. Сгенерируйте вопросы снова."
        )
    return normalized
