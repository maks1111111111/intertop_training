"""Tests for applying AI lesson practical-task previews."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ai.practical_task_generation_service import PracticalTaskGenerationService
from app.content.runtime import ContentRuntime
from app.web.admin_lesson_practical_task_apply_service import (
    AdminLessonPracticalTaskApplyError,
    AdminLessonPracticalTaskApplyRequest,
    AdminLessonPracticalTaskApplyService,
)
from app.web.admin_lesson_practical_task_preview_service import (
    AdminLessonPracticalTaskPreviewService,
)
from app.web.admin_lesson_practical_task_preview_store import (
    AdminLessonPracticalTaskPreviewStore,
    StoredPreviewPracticalTask,
)
from tests.web.test_admin_lesson_practical_task_preview import (
    _create_client_with_mock,
    _mock_practical_task_result,
    _preview_url,
    _write_rich_lesson_course,
)


def _apply_url(slug: str = "alpha", lesson_id: str = "lesson_01") -> str:
    return f"/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task/apply"


def _generate_and_get_preview_id(client: TestClient) -> str:
    response = client.post(_preview_url())
    response.raise_for_status()
    marker = 'name="preview_id" value="'
    start = response.text.index(marker) + len(marker)
    end = response.text.index('"', start)
    return response.text[start:end]


class AdminLessonPracticalTaskApplySuccessTests(unittest.TestCase):
    """Verify successful apply workflow."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.client, _, self.db_tmp, self.upload_tmp = _create_client_with_mock(
            self.courses_dir
        )
        self.preview_store = self.client.app.state.admin_lesson_practical_task_preview_store
        self.client.app.state.admin_lesson_practical_task_apply_service = (
            AdminLessonPracticalTaskApplyService(
                self.courses_dir,
                self.client.app.state.content_runtime,
                self.preview_store,
            )
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_apply_redirects_303_to_lesson_edit(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        response = self.client.post(
            _apply_url(),
            data={"preview_id": preview_id},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/alpha/lessons/lesson_01/edit",
        )

    def test_structured_practical_task_persisted(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data={"preview_id": preview_id})
        lesson_json = json.loads(
            (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        task = lesson_json["structured_practical_task"]
        self.assertEqual(task["title"], "Проверка рабочего места")
        self.assertEqual(
            task["description"],
            "Осмотрите рабочую зону перед началом смены.",
        )
        self.assertEqual(
            task["expected_result"],
            "Все риски обнаружены и устранены.",
        )
        self.assertEqual(task["estimated_minutes"], 15)

    def test_practical_task_legacy_field_updated(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data={"preview_id": preview_id})
        lesson_json = json.loads(
            (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            lesson_json["practical_task"],
            "Осмотрите рабочую зону перед началом смены.",
        )

    def test_existing_lesson_fields_preserved(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data={"preview_id": preview_id})
        lesson_json = json.loads(
            (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["title"], "First lesson")
        self.assertEqual(lesson_json["order"], 1)
        self.assertEqual(
            lesson_json["description"],
            "Unique lesson body for practical task generation.",
        )
        self.assertEqual(lesson_json["checklist"], ["Item one"])
        self.assertEqual(lesson_json["key_takeaways"], ["Takeaway one"])
        self.assertEqual(lesson_json["application_tips"], ["Tip one"])

    def test_course_json_unchanged(self) -> None:
        course_path = self.courses_dir / "alpha" / "course.json"
        before = json.loads(course_path.read_text(encoding="utf-8"))
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data={"preview_id": preview_id})
        after = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertEqual(before, after)

    def test_runtime_refresh_called_after_success(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        with patch(
            "app.web.admin_lesson_practical_task_apply_service.RuntimeRefreshService"
        ) as mock_refresh:
            mock_refresh.return_value.refresh.return_value = None
            self.client.post(_apply_url(), data={"preview_id": preview_id})
            mock_refresh.return_value.refresh.assert_called_once()

    def test_reused_preview_id_rejected(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data={"preview_id": preview_id})
        response = self.client.post(_apply_url(), data={"preview_id": preview_id})
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Предпросмотр задания недоступен. Сгенерируйте задание снова.",
            response.text,
        )

    def test_lesson_unchanged_before_apply(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        before = lesson_path.read_text(encoding="utf-8")
        self.client.post(_preview_url())
        after = lesson_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)


class AdminLessonPracticalTaskApplyValidationTests(unittest.TestCase):
    """Verify apply validation and error handling."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.runtime = ContentRuntime(self.courses_dir)
        self.runtime.refresh()
        self.preview_store = AdminLessonPracticalTaskPreviewStore()
        self.apply_service = AdminLessonPracticalTaskApplyService(
            self.courses_dir,
            self.runtime,
            self.preview_store,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unknown_preview_id_rejected(self) -> None:
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id="a" * 32,
                )
            )
        self.assertIn("Предпросмотр задания недоступен", ctx.exception.message)

    def test_malformed_preview_id_rejected(self) -> None:
        with self.assertRaises(AdminLessonPracticalTaskApplyError):
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id="../evil",
                )
            )

    def test_preview_slug_mismatch_rejected(self) -> None:
        mock_service = MagicMock(spec=PracticalTaskGenerationService)
        mock_service.generate_practical_task.return_value = _mock_practical_task_result()
        preview_service = AdminLessonPracticalTaskPreviewService(
            self.runtime,
            preview_store=self.preview_store,
            generation_service=mock_service,
        )
        preview_id = preview_service.generate_preview("alpha", "lesson_01").preview_id
        with self.assertRaises(AdminLessonPracticalTaskApplyError):
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="other",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                )
            )

    def test_malformed_lesson_json_not_modified(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        lesson_path.write_text("{not json", encoding="utf-8")
        preview_id = self.preview_store.save(
            "alpha",
            "lesson_01",
            StoredPreviewPracticalTask(
                title="Task title",
                description="Task description",
                expected_result="Task result",
            ),
        )
        with self.assertRaises(AdminLessonPracticalTaskApplyError):
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                )
            )
        self.assertEqual(lesson_path.read_text(encoding="utf-8"), "{not json")

    def test_write_failure_does_not_refresh(self) -> None:
        mock_service = MagicMock(spec=PracticalTaskGenerationService)
        mock_service.generate_practical_task.return_value = _mock_practical_task_result()
        preview_service = AdminLessonPracticalTaskPreviewService(
            self.runtime,
            preview_store=self.preview_store,
            generation_service=mock_service,
        )
        preview_id = preview_service.generate_preview("alpha", "lesson_01").preview_id
        with patch(
            "app.web.admin_lesson_practical_task_apply_service._atomic_write_json",
            side_effect=OSError("disk full"),
        ), patch(
            "app.web.admin_lesson_practical_task_apply_service.RuntimeRefreshService"
        ) as mock_refresh:
            with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
                self.apply_service.apply_preview(
                    AdminLessonPracticalTaskApplyRequest(
                        slug="alpha",
                        lesson_id="lesson_01",
                        preview_id=preview_id,
                    )
                )
            self.assertIn("Не удалось сохранить изменения", ctx.exception.message)
            mock_refresh.assert_not_called()

    def test_traversal_like_slug_rejected(self) -> None:
        with self.assertRaises(AdminLessonPracticalTaskApplyError):
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="../evil",
                    lesson_id="lesson_01",
                    preview_id="a" * 32,
                )
            )


class AdminLessonPracticalTaskApplyHttpTests(unittest.TestCase):
    """HTTP-level apply tests."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.client, _, self.db_tmp, self.upload_tmp = _create_client_with_mock(
            self.courses_dir
        )
        self.client.app.state.admin_lesson_practical_task_apply_service = (
            AdminLessonPracticalTaskApplyService(
                self.courses_dir,
                self.client.app.state.content_runtime,
                self.client.app.state.admin_lesson_practical_task_preview_store,
            )
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_no_filesystem_path_in_error_html(self) -> None:
        response = self.client.post(
            _apply_url(),
            data={"preview_id": "b" * 32},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(self.courses_dir), response.text)

    def test_lesson_edit_page_has_generate_practical_task_link(self) -> None:
        response = self.client.get("/admin/courses/alpha/lessons/lesson_01/edit")
        self.assertEqual(response.status_code, 200)
        self.assertIn("generate-practical-task", response.text)
        self.assertIn("Сгенерировать практическое задание AI", response.text)


if __name__ == "__main__":
    unittest.main()
