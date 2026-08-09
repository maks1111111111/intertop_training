"""Tests for admin AI lesson practical-task preview generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ai.practical_task_generation_interfaces import PracticalTaskGenerationResult
from app.ai.practical_task_generation_service import PracticalTaskGenerationService
from app.content.practical_task import PracticalTask
from app.content.runtime import ContentRuntime
from app.web.admin_lesson_practical_task_preview_service import (
    AdminLessonPracticalTaskPreviewError,
    AdminLessonPracticalTaskPreviewService,
)
from app.web.admin_lesson_practical_task_preview_store import (
    AdminLessonPracticalTaskPreviewStore,
)
from tests.web.test_web_ui import _create_test_app


def _preview_url(slug: str = "alpha", lesson_id: str = "lesson_01") -> str:
    return f"/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task"


def _write_rich_lesson_course(courses_dir: Path, slug: str = "alpha") -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": "Alpha Course",
                "description": "Course overview.",
                "status": "published",
                "language": "ru",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps(
            {
                "title": "First lesson",
                "order": 1,
                "description": "Unique lesson body for practical task generation.",
                "practical_task": "",
                "checklist": ["Item one"],
                "key_takeaways": ["Takeaway one"],
                "application_tips": ["Tip one"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _mock_practical_task_result() -> PracticalTaskGenerationResult:
    return PracticalTaskGenerationResult(
        task=PracticalTask(
            title="Проверка рабочего места",
            description="Осмотрите рабочую зону перед началом смены.",
            expected_result="Все риски обнаружены и устранены.",
            estimated_minutes=15,
        )
    )


def _create_client_with_mock(
    courses_dir: Path,
) -> tuple[TestClient, MagicMock, tempfile.TemporaryDirectory, tempfile.TemporaryDirectory]:
    app, db_tmp, db_path, upload_tmp = _create_test_app(courses_dir)
    mock_generation_service = MagicMock(spec=PracticalTaskGenerationService)
    mock_generation_service.generate_practical_task.return_value = (
        _mock_practical_task_result()
    )
    preview_store = AdminLessonPracticalTaskPreviewStore()
    app.state.admin_lesson_practical_task_preview_store = preview_store
    app.state.admin_lesson_practical_task_preview_service = (
        AdminLessonPracticalTaskPreviewService(
            app.state.content_runtime,
            preview_store=preview_store,
            generation_service=mock_generation_service,
        )
    )
    client = TestClient(app)
    return client, mock_generation_service, db_tmp, upload_tmp


class AdminLessonPracticalTaskPreviewGetTests(unittest.TestCase):
    """Verify GET preview page behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.client, _, self.db_tmp, self.upload_tmp = _create_client_with_mock(
            self.courses_dir
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_get_returns_200(self) -> None:
        response = self.client.get(_preview_url())
        self.assertEqual(response.status_code, 200)

    def test_page_contains_heading(self) -> None:
        response = self.client.get(_preview_url())
        self.assertIn("Генерация практического задания AI", response.text)

    def test_page_contains_course_and_lesson_context(self) -> None:
        response = self.client.get(_preview_url())
        self.assertIn("Alpha Course", response.text)
        self.assertIn("First lesson", response.text)

    def test_page_contains_preview_notice(self) -> None:
        response = self.client.get(_preview_url())
        self.assertIn("Практическое задание будет только сгенерировано", response.text)
        self.assertIn("Курс изменен не будет", response.text)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.get(_preview_url(slug="missing"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_unknown_lesson_returns_404(self) -> None:
        response = self.client.get(_preview_url(lesson_id="lesson_99"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Урок не найден", response.text)

    def test_no_filesystem_path_in_html(self) -> None:
        response = self.client.get(_preview_url())
        self.assertNotIn(str(self.courses_dir), response.text)


class AdminLessonPracticalTaskPreviewPostTests(unittest.TestCase):
    """Verify POST preview generation behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.client, self.mock_service, self.db_tmp, self.upload_tmp = (
            _create_client_with_mock(self.courses_dir)
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_post_returns_200(self) -> None:
        response = self.client.post(_preview_url())
        self.assertEqual(response.status_code, 200)

    def test_ai_service_called(self) -> None:
        self.client.post(_preview_url())
        self.mock_service.generate_practical_task.assert_called_once()

    def test_preview_displays_generated_task(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn("Проверка рабочего места", response.text)
        self.assertIn("Осмотрите рабочую зону", response.text)
        self.assertIn("Все риски обнаружены", response.text)
        self.assertIn("15 мин.", response.text)

    def test_preview_contains_apply_form(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn('name="preview_id"', response.text)
        self.assertIn("Применить", response.text)

    def test_preview_contains_regenerate_button(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn("Сгенерировать снова", response.text)

    def test_lesson_json_unchanged_after_generation(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        before = lesson_path.read_text(encoding="utf-8")
        self.client.post(_preview_url())
        after = lesson_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_course_json_unchanged_after_generation(self) -> None:
        course_path = self.courses_dir / "alpha" / "course.json"
        before = course_path.read_text(encoding="utf-8")
        self.client.post(_preview_url())
        after = course_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_ai_generation_failure_shows_safe_error(self) -> None:
        self.mock_service.generate_practical_task.side_effect = RuntimeError("boom")
        response = self.client.post(_preview_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сгенерировать практическое задание.", response.text)
        self.assertNotIn("boom", response.text)


class AdminLessonPracticalTaskPreviewServiceTests(unittest.TestCase):
    """Direct unit tests for preview service."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.runtime = ContentRuntime(self.courses_dir)
        self.runtime.refresh()
        self.preview_store = AdminLessonPracticalTaskPreviewStore()
        self.mock_service = MagicMock(spec=PracticalTaskGenerationService)
        self.mock_service.generate_practical_task.return_value = (
            _mock_practical_task_result()
        )
        self.service = AdminLessonPracticalTaskPreviewService(
            self.runtime,
            preview_store=self.preview_store,
            generation_service=self.mock_service,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_traversal_like_slug_rejected(self) -> None:
        self.assertEqual(
            self.service.get_not_found_reason("../evil", "lesson_01"),
            "course",
        )

    def test_traversal_like_lesson_id_rejected(self) -> None:
        self.assertEqual(
            self.service.get_not_found_reason("alpha", "../evil"),
            "lesson",
        )


if __name__ == "__main__":
    unittest.main()
