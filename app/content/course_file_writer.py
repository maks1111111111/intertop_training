"""Write course drafts to the filesystem as Content Engine layout.

Persists :class:`CourseDraft` metadata as ``course.json`` and per-lesson
``lesson.json`` files compatible with the runtime Content Engine contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.content.contract import COURSE_JSON_FILENAME, LESSON_JSON_FILENAME
from app.content.course_writer import CourseDraft
from app.content.practical_task import PracticalTask


class CourseFileWriter:
    """Persist a :class:`CourseDraft` as course and lesson JSON files."""

    def write(self, draft: CourseDraft, destination: Path) -> Path:
        """Write course metadata and lesson manifests under ``destination``.

        Creates ``course.json`` and ``lesson_XX/lesson.json`` files using
        runtime-compatible field names (``order``, ``title``, ``description``).

        Args:
            draft: In-memory course draft from :class:`CourseWriter`.
            destination: Course root directory to create or populate.

        Returns:
            The resolved course directory path.

        Raises:
            NotADirectoryError: If ``destination`` exists and is not a directory.
        """
        course_dir = destination
        if course_dir.exists() and not course_dir.is_dir():
            raise NotADirectoryError(
                f"Course destination must be a directory: {course_dir}"
            )

        course_dir.mkdir(parents=True, exist_ok=True)

        course_manifest = {
            "title": draft.title,
            "description": draft.description,
            "language": draft.language,
            "slug": draft.slug,
        }
        _write_json(course_dir / COURSE_JSON_FILENAME, course_manifest)

        for index, lesson in enumerate(draft.lessons, start=1):
            lesson_dir = course_dir / f"lesson_{index:02d}"
            lesson_dir.mkdir(parents=True, exist_ok=True)

            lesson_manifest = {
                "order": index,
                "title": lesson.title,
                "description": lesson.content,
                "practical_task": lesson.practical_task,
                "structured_practical_task": _serialize_structured_practical_task(
                    lesson.structured_practical_task
                ),
                "checklist": list(lesson.checklist),
                "common_mistakes": list(lesson.common_mistakes),
                "key_takeaways": list(lesson.key_takeaways),
                "application_tips": list(lesson.application_tips),
            }
            _write_json(lesson_dir / LESSON_JSON_FILENAME, lesson_manifest)

        return course_dir


def _serialize_structured_practical_task(
    task: Optional[PracticalTask],
) -> Optional[dict]:
    if task is None:
        return None
    return {
        "title": task.title,
        "description": task.description,
        "expected_result": task.expected_result,
        "estimated_minutes": task.estimated_minutes,
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
