"""Tests for applying selected AI lesson question previews to course quiz."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ai.quiz_service import QuizGenerationService
from app.content.runtime import ContentRuntime
from app.web.admin_lesson_question_apply_service import (
    AdminLessonQuestionApplyError,
    AdminLessonQuestionApplyRequest,
    AdminLessonQuestionApplyService,
)
from app.web.admin_lesson_question_preview_service import AdminLessonQuestionPreviewService
from app.web.admin_lesson_question_preview_store import AdminLessonQuestionPreviewStore
from tests.web.test_admin_lesson_question_preview import (
    _create_client_with_mock,
    _mock_quiz_result,
    _preview_url,
    _write_rich_lesson_course,
)
from tests.web.test_web_ui import (
    _create_test_app,
    _write_quiz_json,
)


def _apply_url(slug: str = "alpha", lesson_id: str = "lesson_01") -> str:
    return f"/admin/courses/{slug}/lessons/{lesson_id}/generate-questions/apply"


def _write_alpha_course_with_quiz(courses_dir: Path) -> None:
    _write_rich_lesson_course(courses_dir, slug="alpha")
    _write_quiz_json(courses_dir / "alpha", "alpha")


def _generate_and_get_preview_id(client: TestClient) -> str:
    response = client.post(_preview_url())
    response.raise_for_status()
    marker = 'name="preview_id" value="'
    start = response.text.index(marker) + len(marker)
    end = response.text.index('"', start)
    return response.text[start:end]


class AdminLessonQuestionApplyUiTests(unittest.TestCase):
    """Verify preview UI exposes apply workflow."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_alpha_course_with_quiz(self.courses_dir)
        self.client, _, self.db_tmp, self.upload_tmp = _create_client_with_mock(
            self.courses_dir
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_generated_preview_contains_checkbox_for_every_question(self) -> None:
        response = self.client.post(_preview_url())
        self.assertEqual(response.text.count('name="selected_questions"'), 2)

    def test_all_questions_selected_by_default(self) -> None:
        response = self.client.post(_preview_url())
        self.assertEqual(response.text.count('name="selected_questions"'), 2)
        self.assertEqual(response.text.count('value="0"'), 1)
        self.assertEqual(response.text.count('value="1"'), 1)
        self.assertEqual(response.text.count("checked"), 2)

    def test_apply_form_exists(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn("Добавить выбранные в итоговый тест", response.text)
        self.assertIn("/generate-questions/apply", response.text)

    def test_preview_id_present(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn('name="preview_id"', response.text)

    def test_no_full_generated_json_in_hidden_fields(self) -> None:
        response = self.client.post(_preview_url())
        self.assertNotIn("What is the main topic?", response.text.split("hidden")[0])
        hidden_sections = [
            part for part in response.text.split("<input") if "hidden" in part
        ]
        for section in hidden_sections:
            self.assertNotIn("Correct answer", section)
            self.assertNotIn("Second preview question?", section)

    def test_regenerate_remains_available(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn("Сгенерировать снова", response.text)


class AdminLessonQuestionApplySuccessTests(unittest.TestCase):
    """Verify successful apply behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_alpha_course_with_quiz(self.courses_dir)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.preview_store = AdminLessonQuestionPreviewStore()
        mock_quiz_service = MagicMock(spec=QuizGenerationService)
        mock_quiz_service.generate_quiz.return_value = _mock_quiz_result()
        self.app.state.admin_lesson_question_preview_store = self.preview_store
        self.app.state.admin_lesson_question_preview_service = (
            AdminLessonQuestionPreviewService(
                self.app.state.content_runtime,
                preview_store=self.preview_store,
                quiz_generation_service=mock_quiz_service,
            )
        )
        self.client = TestClient(self.app)
        self.quiz_path = self.courses_dir / "alpha" / "quiz.json"
        self.before_quiz = json.loads(self.quiz_path.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_selected_questions_appended_to_quiz(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        with patch(
            "app.services.runtime_refresh_service.RuntimeRefreshService.refresh"
        ) as mock_refresh:
            response = self.client.post(
                _apply_url(),
                data={
                    "preview_id": preview_id,
                    "selected_questions": ["0"],
                },
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        mock_refresh.assert_called_once()

        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["questions"]), len(self.before_quiz["questions"]) + 1)
        self.assertEqual(payload["questions"][-1]["text"], "What is the main topic?")

    def test_unselected_questions_not_appended(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["1"],
            },
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        texts = [item["text"] for item in payload["questions"]]
        self.assertIn("Second preview question?", texts)
        self.assertNotIn("What is the main topic?", texts[-len(self.before_quiz["questions"]) :])

    def test_existing_questions_unchanged(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        for before, after in zip(self.before_quiz["questions"], payload["questions"]):
            self.assertEqual(before, after)

    def test_question_ids_continue_from_max_existing(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0", "1"],
            },
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        new_ids = [item["id"] for item in payload["questions"][-2:]]
        self.assertEqual(new_ids, ["q3", "q4"])

    def test_added_lesson_field_matches_current_lesson(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["lesson"], "lesson_01")

    def test_question_fields_persist(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        added = json.loads(self.quiz_path.read_text(encoding="utf-8"))["questions"][-1]
        self.assertEqual(added["text"], "What is the main topic?")
        self.assertEqual(added["options"][1]["text"], "Correct answer")
        self.assertEqual(added["correct_option_ids"], ["b"])
        self.assertEqual(added["type"], "single_choice")

    def test_quiz_settings_unchanged(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        for key in ("id", "title", "passing_score", "randomize_options"):
            if key in self.before_quiz:
                self.assertEqual(payload[key], self.before_quiz[key])
        if "randomize_questions" in self.before_quiz:
            self.assertEqual(
                payload["randomize_questions"],
                self.before_quiz["randomize_questions"],
            )
        if "version" in self.before_quiz:
            self.assertEqual(payload["version"], self.before_quiz["version"])

    def test_unknown_quiz_root_field_preserved(self) -> None:
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        payload["custom_future_field"] = {"x": 1}
        self.quiz_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        updated = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["custom_future_field"], {"x": 1})

    def test_course_json_unchanged(self) -> None:
        course_path = self.courses_dir / "alpha" / "course.json"
        before = course_path.read_text(encoding="utf-8")
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        self.assertEqual(course_path.read_text(encoding="utf-8"), before)

    def test_lesson_json_unchanged(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        before = lesson_path.read_text(encoding="utf-8")
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        self.assertEqual(lesson_path.read_text(encoding="utf-8"), before)

    def test_redirects_to_quiz_edit(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        response = self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/courses/alpha/quiz/edit")

    def test_added_question_visible_in_admin_quiz_editor(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        self.app.state.content_runtime.refresh()
        response = self.client.get("/admin/courses/alpha/quiz/edit")
        self.assertIn("What is the main topic?", response.text)

    def test_added_question_visible_to_student_quiz(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        self.app.state.content_runtime.refresh()
        response = self.client.get("/courses/alpha/quiz")
        self.assertEqual(response.status_code, 200)
        self.assertIn("What is the main topic?", response.text)


class AdminLessonQuestionApplyValidationTests(unittest.TestCase):
    """Verify apply validation and security behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_alpha_course_with_quiz(self.courses_dir)
        self.preview_store = AdminLessonQuestionPreviewStore()
        self.runtime = ContentRuntime(self.courses_dir)
        self.mock_quiz_service = MagicMock(spec=QuizGenerationService)
        self.mock_quiz_service.generate_quiz.return_value = _mock_quiz_result()
        self.preview_service = AdminLessonQuestionPreviewService(
            self.runtime,
            preview_store=self.preview_store,
            quiz_generation_service=self.mock_quiz_service,
        )
        self.apply_service = AdminLessonQuestionApplyService(
            self.courses_dir,
            self.runtime,
            self.preview_store,
        )
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.app.state.admin_lesson_question_preview_store = self.preview_store
        self.app.state.admin_lesson_question_preview_service = self.preview_service
        self.client = TestClient(self.app)
        self.quiz_path = self.courses_dir / "alpha" / "quiz.json"

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def _preview_id(self) -> str:
        preview = self.preview_service.generate_preview("alpha", "lesson_01")
        return preview.preview_id

    def test_empty_selection_rejected(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data={"preview_id": preview_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите хотя бы один вопрос.", response.text)

    def test_unknown_preview_id_rejected(self) -> None:
        response = self.client.post(
            _apply_url(),
            data={
                "preview_id": "0" * 32,
                "selected_questions": ["0"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)

    def test_reused_preview_id_rejected_after_success(self) -> None:
        preview_id = self._preview_id()
        self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
            follow_redirects=False,
        )
        response = self.client.post(
            _apply_url(),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
        )
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)

    def test_preview_slug_mismatch_rejected(self) -> None:
        other_dir = self.courses_dir / "beta"
        other_dir.mkdir()
        (other_dir / "course.json").write_text(
            json.dumps({"title": "Beta", "status": "published", "language": "ru"}),
            encoding="utf-8",
        )
        lesson_dir = other_dir / "lesson_01"
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            json.dumps({"title": "Beta lesson", "order": 1, "description": "Body"}),
            encoding="utf-8",
        )
        _write_quiz_json(other_dir, "beta")
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url("beta"),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
        )
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)

    def test_preview_lesson_mismatch_rejected(self) -> None:
        lesson_dir = self.courses_dir / "alpha" / "lesson_02"
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            json.dumps({"title": "Second", "order": 2, "description": "Body"}),
            encoding="utf-8",
        )
        self.app.state.content_runtime.refresh()
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(lesson_id="lesson_02"),
            data={
                "preview_id": preview_id,
                "selected_questions": ["0"],
            },
        )
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)

    def test_missing_quiz_rejected(self) -> None:
        no_quiz_dir = self.courses_dir / "no-quiz"
        no_quiz_dir.mkdir()
        (no_quiz_dir / "course.json").write_text(
            json.dumps({"title": "No quiz", "status": "published", "language": "ru"}),
            encoding="utf-8",
        )
        lesson_dir = no_quiz_dir / "lesson_01"
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            json.dumps({"title": "Lesson", "order": 1, "description": "Body"}),
            encoding="utf-8",
        )
        runtime = ContentRuntime(self.courses_dir)
        preview_service = AdminLessonQuestionPreviewService(
            runtime,
            preview_store=self.preview_store,
            quiz_generation_service=self.mock_quiz_service,
        )
        preview = preview_service.generate_preview("no-quiz", "lesson_01")
        with self.assertRaises(AdminLessonQuestionApplyError) as ctx:
            AdminLessonQuestionApplyService(
                self.courses_dir,
                runtime,
                self.preview_store,
            ).apply_selected_questions(
                AdminLessonQuestionApplyRequest(
                    slug="no-quiz",
                    lesson_id="lesson_01",
                    preview_id=preview.preview_id,
                    selected_indexes=(0,),
                )
            )
        self.assertIn("Итоговый тест для курса не найден.", str(ctx.exception.message))

    def test_malformed_quiz_rejected(self) -> None:
        self.quiz_path.write_text("{bad", encoding="utf-8")
        preview_id = self._preview_id()
        with self.assertRaises(AdminLessonQuestionApplyError) as ctx:
            self.apply_service.apply_selected_questions(
                AdminLessonQuestionApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id=preview_id,
                    selected_indexes=(0,),
                )
            )
        self.assertIn("Не удалось загрузить данные теста.", str(ctx.exception.message))

    def test_write_failure_safe(self) -> None:
        preview_id = self._preview_id()
        with patch(
            "app.web.admin_lesson_question_apply_service._atomic_write_json",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaises(AdminLessonQuestionApplyError) as ctx:
                self.apply_service.apply_selected_questions(
                    AdminLessonQuestionApplyRequest(
                        slug="alpha",
                        lesson_id="lesson_01",
                        preview_id=preview_id,
                        selected_indexes=(0,),
                    )
                )
        self.assertIn("Не удалось сохранить изменения.", str(ctx.exception.message))

    def test_write_failure_does_not_refresh(self) -> None:
        preview_id = self._preview_id()
        with patch(
            "app.web.admin_lesson_question_apply_service._atomic_write_json",
            side_effect=OSError("disk full"),
        ), patch(
            "app.services.runtime_refresh_service.RuntimeRefreshService.refresh"
        ) as mock_refresh:
            with self.assertRaises(AdminLessonQuestionApplyError):
                self.apply_service.apply_selected_questions(
                    AdminLessonQuestionApplyRequest(
                        slug="alpha",
                        lesson_id="lesson_01",
                        preview_id=preview_id,
                        selected_indexes=(0,),
                    )
                )
        mock_refresh.assert_not_called()

    def test_no_filesystem_path_leaked(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data={"preview_id": preview_id},
        )
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)

    def test_traversal_like_slug_rejected(self) -> None:
        with self.assertRaises(AdminLessonQuestionApplyError):
            self.apply_service.apply_selected_questions(
                AdminLessonQuestionApplyRequest(
                    slug="../alpha",
                    lesson_id="lesson_01",
                    preview_id="a" * 32,
                    selected_indexes=(0,),
                )
            )

    def test_invalid_request_does_not_modify_quiz(self) -> None:
        before = self.quiz_path.read_text(encoding="utf-8")
        preview_id = self._preview_id()
        self.client.post(
            _apply_url(),
            data={"preview_id": preview_id},
        )
        self.assertEqual(self.quiz_path.read_text(encoding="utf-8"), before)


class AdminLessonQuestionApplyServiceUnitTests(unittest.TestCase):
    """Direct unit tests for apply service helpers."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_alpha_course_with_quiz(self.courses_dir)
        self.preview_store = AdminLessonQuestionPreviewStore()
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminLessonQuestionApplyService(
            self.courses_dir,
            self.runtime,
            self.preview_store,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_malformed_preview_id_rejected(self) -> None:
        with self.assertRaises(AdminLessonQuestionApplyError):
            self.service.apply_selected_questions(
                AdminLessonQuestionApplyRequest(
                    slug="alpha",
                    lesson_id="lesson_01",
                    preview_id="not-valid",
                    selected_indexes=(0,),
                )
            )


if __name__ == "__main__":
    unittest.main()
