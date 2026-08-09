"""In-memory store for AI-generated lesson practical-task previews."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

_PREVIEW_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class StoredPreviewPracticalTask:
    """Structured preview practical task payload safe for later persistence."""

    title: str
    description: str
    expected_result: str
    estimated_minutes: Optional[int] = None


@dataclass
class LessonPracticalTaskPreviewRecord:
    """Server-side preview session bound to one course lesson."""

    preview_id: str
    slug: str
    lesson_id: str
    task: StoredPreviewPracticalTask
    consumed: bool = False


class AdminLessonPracticalTaskPreviewStoreError(Exception):
    """Raised when practical-task preview store access is invalid."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AdminLessonPracticalTaskPreviewStore:
    """Single-process in-memory preview store for AI lesson practical tasks."""

    def __init__(self) -> None:
        self._records: dict[str, LessonPracticalTaskPreviewRecord] = {}

    def save(
        self,
        slug: str,
        lesson_id: str,
        task: StoredPreviewPracticalTask,
    ) -> str:
        """Persist a generated preview and return its opaque identifier."""
        preview_id = uuid.uuid4().hex
        self._records[preview_id] = LessonPracticalTaskPreviewRecord(
            preview_id=preview_id,
            slug=slug,
            lesson_id=lesson_id,
            task=task,
        )
        return preview_id

    def get(self, preview_id: str) -> Optional[LessonPracticalTaskPreviewRecord]:
        """Return an active preview record, or ``None`` if missing or consumed."""
        normalized = _validate_preview_id(preview_id)
        record = self._records.get(normalized)
        if record is None or record.consumed:
            return None
        return record

    def consume(self, preview_id: str) -> Optional[LessonPracticalTaskPreviewRecord]:
        """Mark a preview as consumed so it cannot be applied again."""
        record = self.get(preview_id)
        if record is None:
            return None
        record.consumed = True
        return record


def _validate_preview_id(raw: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized or not _PREVIEW_ID_PATTERN.match(normalized):
        raise AdminLessonPracticalTaskPreviewStoreError(
            "Предпросмотр задания недоступен. Сгенерируйте задание снова."
        )
    return normalized
