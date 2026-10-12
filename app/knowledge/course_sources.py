"""Expose published course materials as tenant-scoped Knowledge Base sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import quote

from app.content.runtime import ContentRuntime
from app.content.runtime_loader import Course, Lesson
from app.knowledge.models import KnowledgeDocumentChunk


_COURSE_DOCUMENT_PREFIX = "course:"


@dataclass(frozen=True)
class CourseKnowledgeSource:
    """A virtual Knowledge Base document backed by one published course."""

    document_id: str
    title: str
    original_filename: str
    view_url: str
    chunks: tuple[KnowledgeDocumentChunk, ...]


class PublishedCourseKnowledgeSource:
    """Build read-only retrieval chunks from one tenant's published runtime."""

    def __init__(self, runtime: ContentRuntime) -> None:
        self._runtime = runtime

    def list_chunks(
        self,
        _db_path: Path,
        company_id: str,
    ) -> Sequence[KnowledgeDocumentChunk]:
        """Return course and lesson text without persisting a duplicate index."""
        return tuple(
            chunk
            for source in self._list_sources(company_id)
            for chunk in source.chunks
        )

    def get_source(
        self,
        _company_id: str,
        document_id: str,
    ) -> CourseKnowledgeSource | None:
        """Resolve a cited virtual document back to its published course."""
        normalized_document_id = str(document_id or "").strip()
        if not normalized_document_id.startswith(_COURSE_DOCUMENT_PREFIX):
            return None
        return next(
            (
                source
                for source in self._list_sources(_company_id)
                if source.document_id == normalized_document_id
            ),
            None,
        )

    def _list_sources(self, company_id: str) -> tuple[CourseKnowledgeSource, ...]:
        normalized_company_id = _require_company_id(company_id)
        sources: list[CourseKnowledgeSource] = []
        for course_index, course in enumerate(self._runtime.get_courses()):
            if course.status != "published":
                continue
            source = _source_from_course(
                normalized_company_id,
                course,
                course_index=course_index,
            )
            if source is not None:
                sources.append(source)
        return tuple(sources)


def _require_company_id(company_id: str) -> str:
    normalized = str(company_id or "").strip()
    if not normalized:
        raise ValueError("company_id must not be empty")
    return normalized


def _source_from_course(
    company_id: str,
    course: Course,
    *,
    course_index: int,
) -> CourseKnowledgeSource | None:
    slug = str(course.slug or "").strip()
    title = str(course.title or "").strip()
    if not slug or not title:
        return None

    document_id = f"{_COURSE_DOCUMENT_PREFIX}{slug}"
    chunks: list[KnowledgeDocumentChunk] = []

    overview_text = _course_overview_text(course)
    if overview_text:
        chunks.append(
            _chunk(
                company_id,
                document_id,
                chunk_index=0,
                text=overview_text,
                synthetic_id=-((course_index + 1) * 10_000),
            )
        )

    for lesson_index, lesson in enumerate(course.lessons, start=1):
        lesson_text = _lesson_text(course, lesson)
        if lesson_text:
            chunks.append(
                _chunk(
                    company_id,
                    document_id,
                    chunk_index=lesson_index,
                    text=lesson_text,
                    synthetic_id=-((course_index + 1) * 10_000 + lesson_index),
                )
            )

    if not chunks:
        return None

    return CourseKnowledgeSource(
        document_id=document_id,
        title=f"Курс: {title}",
        original_filename="Опубликованные материалы курса",
        view_url=f"/courses/{quote(slug, safe='')}",
        chunks=tuple(chunks),
    )


def _chunk(
    company_id: str,
    document_id: str,
    *,
    chunk_index: int,
    text: str,
    synthetic_id: int,
) -> KnowledgeDocumentChunk:
    return KnowledgeDocumentChunk(
        id=synthetic_id,
        company_id=company_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        start_char=0,
        end_char=len(text),
        created_at="",
    )


def _course_overview_text(course: Course) -> str:
    parts = [f"Курс: {course.title}"]
    description = str(course.description or "").strip()
    if description:
        parts.append(f"Описание курса: {description}")
    return "\n".join(parts)


def _lesson_text(course: Course, lesson: Lesson) -> str:
    title = str(lesson.title or "").strip()
    if not title:
        return ""

    parts = [f"Курс: {course.title}", f"Урок: {title}"]
    _append_text(parts, "Описание урока", lesson.description)
    _append_text(parts, "Практическое задание", lesson.practical_task)
    _append_items(parts, "Контрольный список", lesson.checklist)
    _append_items(parts, "Частые ошибки", lesson.common_mistakes)
    _append_items(parts, "Ключевые выводы", lesson.key_takeaways)
    _append_items(parts, "Советы по применению", lesson.application_tips)
    return "\n".join(parts)


def _append_text(parts: list[str], label: str, value: str) -> None:
    normalized = str(value or "").strip()
    if normalized:
        parts.append(f"{label}: {normalized}")


def _append_items(parts: list[str], label: str, values: Sequence[str]) -> None:
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if normalized:
        parts.append(f"{label}: " + "; ".join(normalized))
