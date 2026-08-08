"""Tests for course read API endpoints."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.content.runtime import ContentRuntime


def _write_course(
    courses_dir: Path,
    slug: str,
    *,
    title: str = "Sample Course",
    description: str = "Course overview for learners.",
    language: str = "ru",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        (
            '{"title": "'
            + title
            + '", "description": "'
            + description
            + '", "status": "published", "language": "'
            + language
            + '"}'
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        '{"title": "First lesson", "order": 1, "description": "Body text."}',
        encoding="utf-8",
    )


class CourseApiTests(unittest.TestCase):
    """Verify read-only course endpoints."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_course(self.courses_dir, "alpha", title="Alpha Course", language="ru")

        self.app = create_app()
        self.app.state.content_runtime = ContentRuntime(self.courses_dir)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_list_courses_returns_200(self) -> None:
        response = self.client.get("/api/v1/courses")

        self.assertEqual(response.status_code, 200)

    def test_list_courses_response_structure(self) -> None:
        response = self.client.get("/api/v1/courses")
        data = response.json()

        self.assertIn("items", data)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(
            data["items"][0],
            {
                "slug": "alpha",
                "title": "Alpha Course",
                "description": "Course overview for learners.",
            },
        )

    def test_get_existing_course_returns_200(self) -> None:
        response = self.client.get("/api/v1/courses/alpha")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "alpha")
        self.assertEqual(data["title"], "Alpha Course")
        self.assertEqual(data["description"], "Course overview for learners.")
        self.assertEqual(data["language"], "ru")
        self.assertEqual(
            data["lessons"],
            [
                {
                    "id": "lesson_01",
                    "title": "First lesson",
                    "order": 1,
                }
            ],
        )

    def test_get_unknown_course_returns_404(self) -> None:
        response = self.client.get("/api/v1/courses/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "course_not_found",
                    "message": "Course not found.",
                }
            },
        )

    def test_root_health_endpoint_is_not_course_list(self) -> None:
        response = self.client.get("/health")

        self.assertNotEqual(response.status_code, 200)

    def test_get_existing_lesson_returns_200(self) -> None:
        response = self.client.get("/api/v1/courses/alpha/lessons/lesson_01")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "lesson_01")
        self.assertEqual(data["title"], "First lesson")
        self.assertEqual(data["order"], 1)
        self.assertEqual(data["content"], "Body text.")
        self.assertEqual(data["practical_task"], "")
        self.assertEqual(data["checklist"], [])
        self.assertEqual(data["common_mistakes"], [])
        self.assertEqual(data["key_takeaways"], [])
        self.assertEqual(data["application_tips"], [])
        self.assertIsNone(data["previous_lesson_id"])
        self.assertIsNone(data["next_lesson_id"])
        self.assertTrue(data["is_first"])
        self.assertTrue(data["is_last"])

    def test_get_lesson_returns_quality_fields(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        lesson_path.write_text(
            json.dumps(
                {
                    "title": "First lesson",
                    "order": 1,
                    "description": "Body text.",
                    "practical_task": "Inspect the work area.",
                    "checklist": ["Wear PPE", "Check equipment"],
                    "common_mistakes": ["Skipping inspection"],
                    "key_takeaways": ["Safety first"],
                    "application_tips": ["Apply the checklist daily"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.app.state.content_runtime.refresh()

        response = self.client.get("/api/v1/courses/alpha/lessons/lesson_01")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": "lesson_01",
                "title": "First lesson",
                "order": 1,
                "content": "Body text.",
                "practical_task": "Inspect the work area.",
                "checklist": ["Wear PPE", "Check equipment"],
                "common_mistakes": ["Skipping inspection"],
                "key_takeaways": ["Safety first"],
                "application_tips": ["Apply the checklist daily"],
                "previous_lesson_id": None,
                "next_lesson_id": None,
                "is_first": True,
                "is_last": True,
            },
        )

    def test_get_lesson_for_unknown_course_returns_404(self) -> None:
        response = self.client.get("/api/v1/courses/missing/lessons/lesson_01")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "course_not_found",
                    "message": "Course not found.",
                }
            },
        )

    def test_get_unknown_lesson_returns_404(self) -> None:
        response = self.client.get("/api/v1/courses/alpha/lessons/lesson_99")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "lesson_not_found",
                    "message": "Lesson not found.",
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
