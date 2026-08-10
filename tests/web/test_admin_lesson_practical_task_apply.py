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


def _default_apply_form(preview_id: str) -> dict[str, str]:
    return {
        "preview_id": preview_id,
        "title": "Проверка рабочего места",
        "description": "Осмотрите рабочую зону перед началом смены.",
        "expected_result": "Все риски обнаружены и устранены.",
        "estimated_minutes": "15",
    }


def _edited_apply_form(preview_id: str) -> dict[str, str]:
    return {
        "preview_id": preview_id,
        "title": "Проверка зоны перед открытием",
        "description": "Проведите самостоятельный осмотр торговой зоны.",
        "expected_result": "Все выявленные риски устранены до открытия магазина.",
        "estimated_minutes": "20",
    }


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
            data=_default_apply_form(preview_id),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/alpha/lessons/lesson_01/edit",
        )

    def test_structured_practical_task_persisted(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data=_default_apply_form(preview_id))
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
        self.client.post(_apply_url(), data=_default_apply_form(preview_id))
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
        self.client.post(_apply_url(), data=_default_apply_form(preview_id))
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
        self.client.post(_apply_url(), data=_default_apply_form(preview_id))
        after = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertEqual(before, after)

    def test_runtime_refresh_called_after_success(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        with patch(
            "app.web.admin_lesson_practical_task_apply_service.RuntimeRefreshService"
        ) as mock_refresh:
            mock_refresh.return_value.refresh.return_value = None
            self.client.post(_apply_url(), data=_default_apply_form(preview_id))
            mock_refresh.return_value.refresh.assert_called_once()

    def test_reused_preview_id_rejected(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data=_default_apply_form(preview_id))
        response = self.client.post(_apply_url(), data=_default_apply_form(preview_id))
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


class AdminLessonPracticalTaskApplyEditedTests(unittest.TestCase):
    """Verify applying admin-edited preview values."""

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

    def test_edited_values_persisted_not_original_ai_values(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data=_edited_apply_form(preview_id))
        lesson_json = json.loads(
            (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        task = lesson_json["structured_practical_task"]
        self.assertEqual(task["title"], "Проверка зоны перед открытием")
        self.assertEqual(
            task["description"],
            "Проведите самостоятельный осмотр торговой зоны.",
        )
        self.assertEqual(
            task["expected_result"],
            "Все выявленные риски устранены до открытия магазина.",
        )
        self.assertEqual(task["estimated_minutes"], 20)

    def test_practical_task_legacy_field_equals_edited_description(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(_apply_url(), data=_edited_apply_form(preview_id))
        lesson_json = json.loads(
            (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            lesson_json["practical_task"],
            "Проведите самостоятельный осмотр торговой зоны.",
        )

    def test_blank_estimated_minutes_omits_field(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        form = _default_apply_form(preview_id)
        form["estimated_minutes"] = ""
        self.client.post(_apply_url(), data=form)
        lesson_json = json.loads(
            (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        task = lesson_json["structured_practical_task"]
        self.assertNotIn("estimated_minutes", task)


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
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="",
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
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="",
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
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="",
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
                    title="Task title",
                    description="Task description",
                    expected_result="Task result",
                    estimated_minutes="",
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
                        title="Task title",
                        description="Task description",
                        expected_result="Task result",
                        estimated_minutes="15",
                    )
                )
            self.assertIn("Не удалось сохранить изменения", ctx.exception.message)
            mock_refresh.assert_not_called()
            record = self.preview_store.get(preview_id)
            self.assertIsNotNone(record)
            self.assertFalse(record.consumed)

    def test_traversal_like_slug_rejected(self) -> None:
        with self.assertRaises(AdminLessonPracticalTaskApplyError):
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="../evil",
                    lesson_id="lesson_01",
                    preview_id="a" * 32,
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="",
                )
            )

    def _save_preview(self) -> str:
        return self.preview_store.save(
            "alpha",
            "lesson_01",
            StoredPreviewPracticalTask(
                title="Task title",
                description="Task description",
                expected_result="Task result",
                estimated_minutes=15,
            ),
        )

    def test_empty_title_rejected(self) -> None:
        preview_id = self._save_preview()
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    title="   ",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="",
                )
            )
        self.assertEqual(ctx.exception.message, "Укажите название практического задания.")

    def test_empty_description_rejected(self) -> None:
        preview_id = self._save_preview()
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    title="Title",
                    description="",
                    expected_result="Result",
                    estimated_minutes="",
                )
            )
        self.assertEqual(ctx.exception.message, "Добавьте описание практического задания.")

    def test_empty_expected_result_rejected(self) -> None:
        preview_id = self._save_preview()
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    title="Title",
                    description="Description",
                    expected_result="  ",
                    estimated_minutes="",
                )
            )
        self.assertEqual(ctx.exception.message, "Укажите критерии приёмки.")

    def test_non_numeric_estimated_minutes_rejected(self) -> None:
        preview_id = self._save_preview()
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="abc",
                )
            )
        self.assertEqual(
            ctx.exception.message,
            "Оценка времени должна быть положительным целым числом.",
        )

    def test_zero_estimated_minutes_rejected(self) -> None:
        preview_id = self._save_preview()
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="0",
                )
            )
        self.assertEqual(
            ctx.exception.message,
            "Оценка времени должна быть положительным целым числом.",
        )

    def test_negative_estimated_minutes_rejected(self) -> None:
        preview_id = self._save_preview()
        with self.assertRaises(AdminLessonPracticalTaskApplyError) as ctx:
            self.apply_service.apply_preview(
                AdminLessonPracticalTaskApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    title="Title",
                    description="Description",
                    expected_result="Result",
                    estimated_minutes="-5",
                )
            )
        self.assertEqual(
            ctx.exception.message,
            "Оценка времени должна быть положительным целым числом.",
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
            data={
                "preview_id": "b" * 32,
                "title": "Title",
                "description": "Description",
                "expected_result": "Result",
                "estimated_minutes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(self.courses_dir), response.text)

    def test_validation_failure_preserves_edited_values(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        form = _edited_apply_form(preview_id)
        form["estimated_minutes"] = "abc"
        response = self.client.post(_apply_url(), data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Оценка времени должна быть положительным целым числом.", response.text)
        self.assertIn('value="Проверка зоны перед открытием"', response.text)
        self.assertIn("Проведите самостоятельный осмотр торговой зоны.", response.text)
        self.assertIn(
            "Все выявленные риски устранены до открытия магазина.",
            response.text,
        )
        self.assertIn('value="abc"', response.text)

    def test_validation_failure_does_not_modify_lesson_json(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        before = lesson_path.read_text(encoding="utf-8")
        preview_id = _generate_and_get_preview_id(self.client)
        form = _default_apply_form(preview_id)
        form["title"] = "   "
        self.client.post(_apply_url(), data=form)
        after = lesson_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_validation_failure_does_not_consume_preview(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        form = _default_apply_form(preview_id)
        form["title"] = ""
        self.client.post(_apply_url(), data=form)
        record = self.client.app.state.admin_lesson_practical_task_preview_store.get(
            preview_id
        )
        self.assertIsNotNone(record)
        self.assertFalse(record.consumed)

    def test_lesson_edit_page_has_generate_practical_task_link(self) -> None:
        response = self.client.get("/admin/courses/alpha/lessons/lesson_01/edit")
        self.assertEqual(response.status_code, 200)
        self.assertIn("generate-practical-task", response.text)
        self.assertIn("Сгенерировать практическое задание AI", response.text)


if __name__ == "__main__":
    unittest.main()
