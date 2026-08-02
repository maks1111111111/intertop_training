"""Convert AI lesson generation results into in-memory course drafts.

Maps :class:`LessonGenerationResult` to :class:`CourseDraft` without writing
files to disk. Slug generation is ASCII-safe; non-Latin titles receive a
unique ``course-<uuid>`` slug to avoid collisions.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

from dataclasses import dataclass
from typing import Optional, Tuple

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.lesson_builder import LessonCandidate

_DEFAULT_COURSE_TITLE = "Imported Course"
_DEFAULT_COURSE_DESCRIPTION = ""
_DEFAULT_COURSE_LANGUAGE = "en"


@dataclass(frozen=True)
class CourseDraft:
    """In-memory course draft produced from AI generation output."""

    slug: str
    title: str
    description: str
    language: str
    lessons: tuple[LessonCandidate, ...]


class CourseWriter:
    """Build a :class:`CourseDraft` from AI lesson generation results."""

    def write(self, result: LessonGenerationResult) -> CourseDraft:
        """Convert a generation result into a course draft.

        Args:
            result: Parsed AI output with lessons and optional course metadata.

        Returns:
            A :class:`CourseDraft` ready for downstream persistence layers.
        """
        title, description, language = _resolve_course_fields(result.course)
        slug = _slugify(title)

        return CourseDraft(
            slug=slug,
            title=title,
            description=description,
            language=language,
            lessons=tuple(result.lessons),
        )


def _resolve_course_fields(
    course: Optional[GeneratedCourseMetadata],
) -> Tuple[str, str, str]:
    if course is None:
        return (
            _DEFAULT_COURSE_TITLE,
            _DEFAULT_COURSE_DESCRIPTION,
            _DEFAULT_COURSE_LANGUAGE,
        )

    title = course.title.strip() if course.title else _DEFAULT_COURSE_TITLE
    description = (
        course.description if course.description is not None else _DEFAULT_COURSE_DESCRIPTION
    )
    return title, description, course.language


def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title.strip())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if slug:
        return slug
    return f"course-{uuid.uuid4().hex[:12]}"
