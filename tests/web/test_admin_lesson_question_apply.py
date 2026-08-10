"""Tests for applying selected AI lesson question previews to course quiz."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ai.quiz_service import QuizGenerationService
from app.content.runtime import ContentRuntime
from app.web.admin_lesson_question_edit_models import AdminLessonQuestionEditInput
from app.web.admin_lesson_question_apply_service import (
    AdminLessonQuestionApplyError,
    AdminLessonQuestionApplyRequest,
    AdminLessonQuestionApplyService,
    parse_question_edits_from_form,
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


def _default_question_edits() -> dict[int, dict[str, object]]:
    return {
        0: {
            "text": "What is the main topic?",
            "options": {
                "a": "Wrong answer",
                "b": "Correct answer",
                "c": "Another wrong",
                "d": "Yet another wrong",
            },
            "correct": "b",
            "explanation": "",
        },
        1: {
            "text": "Second preview question?",
            "options": {
                "a": "Option A",
                "b": "Option B",
                "c": "Option C",
                "d": "Option D",
            },
            "correct": "a",
            "explanation": "",
        },
    }


def _apply_form_data(
    preview_id: str,
    selected: list[str] | None = None,
    *,
    question_edits: dict[int, dict[str, object]] | None = None,
) -> dict[str, object]:
    if selected is None:
        selected = ["0", "1"]
    edits = _default_question_edits()
    if question_edits:
        for index, override in question_edits.items():
            merged = dict(edits.get(index, {}))
            options_override = override.get("options")
            if options_override is not None:
                merged_options = dict(merged.get("options", {}))
                merged_options.update(options_override)
                merged["options"] = merged_options
            for key, value in override.items():
                if key != "options":
                    merged[key] = value
            edits[index] = merged

    data: dict[str, object] = {
        "preview_id": preview_id,
        "selected_questions": selected,
    }
    for index, question in edits.items():
        data[f"question_{index}_text"] = str(question["text"])
        data[f"question_{index}_explanation"] = str(question.get("explanation", ""))
        data[f"question_{index}_correct_option"] = str(question["correct"])
        for option_id, option_text in question["options"].items():
            data[f"question_{index}_option_{option_id}"] = str(option_text)
    return data


def _default_edited_questions() -> tuple[AdminLessonQuestionEditInput, ...]:
    return (
        AdminLessonQuestionEditInput(
            index=0,
            text="What is the main topic?",
            option_texts=(
                ("a", "Wrong answer"),
                ("b", "Correct answer"),
                ("c", "Another wrong"),
                ("d", "Yet another wrong"),
            ),
            correct_option_id="b",
            explanation="",
        ),
        AdminLessonQuestionEditInput(
            index=1,
            text="Second preview question?",
            option_texts=(
                ("a", "Option A"),
                ("b", "Option B"),
                ("c", "Option C"),
                ("d", "Option D"),
            ),
            correct_option_id="a",
            explanation="",
        ),
    )


def _apply_request(
    preview_id: str,
    *,
    slug: str = "alpha",
    lesson_id: str = "lesson_01",
    selected_indexes: tuple[int, ...] = (0,),
    edited_questions: tuple[AdminLessonQuestionEditInput, ...] | None = None,
) -> AdminLessonQuestionApplyRequest:
    return AdminLessonQuestionApplyRequest(
        slug=slug,
        lesson_id=lesson_id,
        preview_id=preview_id,
        selected_indexes=selected_indexes,
        edited_questions=edited_questions or _default_edited_questions(),
    )


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
        checked_boxes = re.findall(
            r'name="selected_questions"[^>]*checked',
            response.text,
        )
        self.assertEqual(len(checked_boxes), 2)

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

    def test_generated_preview_contains_editable_question_text(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn('name="question_0_text"', response.text)
        self.assertIn('name="question_1_text"', response.text)

    def test_generated_preview_contains_editable_option_controls(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn('name="question_0_option_a"', response.text)
        self.assertIn('name="question_0_option_b"', response.text)

    def test_generated_preview_contains_correct_answer_radios(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn('name="question_0_correct_option"', response.text)
        self.assertIn('value="b"', response.text)

    def test_generated_preview_contains_editable_explanation(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn('name="question_0_explanation"', response.text)

    def test_ai_generated_values_appear_in_editable_controls(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn("What is the main topic?", response.text)
        self.assertIn("Correct answer", response.text)


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
                data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data(preview_id, selected=["1"]),
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
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        for before, after in zip(self.before_quiz["questions"], payload["questions"]):
            self.assertEqual(before, after)

    def test_question_ids_continue_from_max_existing(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0", "1"]),
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        new_ids = [item["id"] for item in payload["questions"][-2:]]
        self.assertEqual(new_ids, ["q3", "q4"])

    def test_added_lesson_field_matches_current_lesson(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["lesson"], "lesson_01")

    def test_question_fields_persist(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        self.assertEqual(course_path.read_text(encoding="utf-8"), before)

    def test_lesson_json_unchanged(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        before = lesson_path.read_text(encoding="utf-8")
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        self.assertEqual(lesson_path.read_text(encoding="utf-8"), before)

    def test_redirects_to_quiz_edit(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/courses/alpha/quiz/edit")

    def test_added_question_visible_in_admin_quiz_editor(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        self.app.state.content_runtime.refresh()
        response = self.client.get("/admin/courses/alpha/quiz/edit")
        self.assertIn("What is the main topic?", response.text)

    def test_added_question_visible_to_student_quiz(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data("0" * 32, selected=["0"]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)

    def test_reused_preview_id_rejected_after_success(self) -> None:
        preview_id = self._preview_id()
        self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
            follow_redirects=False,
        )
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data(preview_id, selected=["0"]),
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
            data=_apply_form_data(preview_id, selected=["0"]),
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
                _apply_request(
                    preview.preview_id,
                    slug="no-quiz",
                    lesson_id="lesson_01",
                )
            )
        self.assertIn("Итоговый тест для курса не найден.", str(ctx.exception.message))

    def test_malformed_quiz_rejected(self) -> None:
        self.quiz_path.write_text("{bad", encoding="utf-8")
        preview_id = self._preview_id()
        with self.assertRaises(AdminLessonQuestionApplyError) as ctx:
            self.apply_service.apply_selected_questions(
                _apply_request(preview_id)
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
                    _apply_request(preview_id)
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
                    _apply_request(preview_id)
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
                _apply_request(
                    "a" * 32,
                    slug="../alpha",
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


class AdminLessonQuestionApplyHardeningTests(unittest.TestCase):
    """Verify hardening for empty selection and preview ownership."""

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
        return self.preview_service.generate_preview("alpha", "lesson_01").preview_id

    def test_empty_selection_preserves_edited_question_text(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=[],
                question_edits={0: {"text": "Preserved empty-selection text"}},
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите хотя бы один вопрос.", response.text)
        self.assertIn("Preserved empty-selection text", response.text)

    def test_empty_selection_preserves_edited_option_text(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=[],
                question_edits={
                    0: {
                        "options": {
                            "a": "Preserved option A",
                            "b": "Preserved option B",
                        }
                    }
                },
            ),
        )
        self.assertIn("Preserved option A", response.text)
        self.assertIn("Preserved option B", response.text)

    def test_empty_selection_preserves_chosen_correct_answer(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=[],
                question_edits={0: {"correct": "c"}},
            ),
        )
        self.assertIn('name="question_0_correct_option"', response.text)
        checked_c = re.search(
            r'name="question_0_correct_option"[^>]*value="c"[^>]*checked',
            response.text,
        )
        self.assertIsNotNone(checked_c)

    def test_empty_selection_leaves_all_checkboxes_unchecked(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=[],
                question_edits={0: {"text": "Still visible"}},
            ),
        )
        checked_boxes = re.findall(
            r'name="selected_questions"[^>]*checked',
            response.text,
        )
        self.assertEqual(checked_boxes, [])

    def test_mismatched_slug_preview_content_not_rendered(self) -> None:
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
        self.app.state.content_runtime.refresh()
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url("beta"),
            data=_apply_form_data(preview_id, selected=["0"]),
        )
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)
        self.assertNotIn("What is the main topic?", response.text)
        self.assertNotIn("Second preview question?", response.text)

    def test_mismatched_lesson_preview_content_not_rendered(self) -> None:
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
            data=_apply_form_data(preview_id, selected=["0"]),
        )
        self.assertIn("Предпросмотр вопросов недоступен.", response.text)
        self.assertNotIn("What is the main topic?", response.text)

    def test_mismatched_preview_remains_unconsumed(self) -> None:
        preview_id = self._preview_id()
        self.client.post(
            _apply_url("beta"),
            data=_apply_form_data(preview_id, selected=["0"]),
        )
        self.assertIsNotNone(self.preview_store.get(preview_id))

    def test_write_failure_leaves_preview_unconsumed(self) -> None:
        preview_id = self._preview_id()
        with patch(
            "app.web.admin_lesson_question_apply_service._atomic_write_json",
            side_effect=OSError("disk full"),
        ), patch(
            "app.services.runtime_refresh_service.RuntimeRefreshService.refresh"
        ) as mock_refresh:
            response = self.client.post(
                _apply_url(),
                data=_apply_form_data(preview_id, selected=["0"]),
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сохранить изменения.", response.text)
        self.assertIsNotNone(self.preview_store.get(preview_id))
        mock_refresh.assert_not_called()


class AdminLessonQuestionApplyEditedTests(unittest.TestCase):
    """Verify applying admin-edited preview question values."""

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

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_edited_question_text_persists(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"text": "Edited preview question?"}},
            ),
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["questions"][-1]["text"], "Edited preview question?")

    def test_edited_option_texts_persist(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={
                    0: {
                        "options": {
                            "a": "Edited A",
                            "b": "Edited B",
                            "c": "Edited C",
                            "d": "Edited D",
                        }
                    }
                },
            ),
            follow_redirects=False,
        )
        added = json.loads(self.quiz_path.read_text(encoding="utf-8"))["questions"][-1]
        self.assertEqual(added["options"][0]["text"], "Edited A")
        self.assertEqual(added["options"][1]["text"], "Edited B")

    def test_edited_correct_answer_persists(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"correct": "c"}},
            ),
            follow_redirects=False,
        )
        added = json.loads(self.quiz_path.read_text(encoding="utf-8"))["questions"][-1]
        self.assertEqual(added["correct_option_ids"], ["c"])

    def test_edited_explanation_persists(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"explanation": "Edited explanation text."}},
            ),
            follow_redirects=False,
        )
        added = json.loads(self.quiz_path.read_text(encoding="utf-8"))["questions"][-1]
        self.assertEqual(added["explanation"], "Edited explanation text.")

    def test_unselected_edited_question_not_added(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={
                    1: {"text": "Should not be added"},
                },
            ),
            follow_redirects=False,
        )
        payload = json.loads(self.quiz_path.read_text(encoding="utf-8"))
        texts = [item["text"] for item in payload["questions"]]
        self.assertNotIn("Should not be added", texts)

    def test_edited_question_visible_to_student_quiz(self) -> None:
        preview_id = _generate_and_get_preview_id(self.client)
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"text": "Student-visible edited question?"}},
            ),
            follow_redirects=False,
        )
        self.app.state.content_runtime.refresh()
        response = self.client.get("/courses/alpha/quiz")
        self.assertIn("Student-visible edited question?", response.text)


class AdminLessonQuestionApplyEditedValidationTests(unittest.TestCase):
    """Verify validation for edited preview question apply."""

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
        return self.preview_service.generate_preview("alpha", "lesson_01").preview_id

    def test_empty_selected_question_text_rejected(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"text": "   "}},
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Введите текст вопроса.", response.text)

    def test_empty_option_rejected(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"options": {"b": "   "}}},
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Заполните все варианты ответа.", response.text)

    def test_invalid_correct_option_rejected(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"correct": "z"}},
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите правильный ответ.", response.text)

    def test_missing_correct_option_rejected(self) -> None:
        preview_id = self._preview_id()
        fields = _apply_form_data(preview_id, selected=["0"])
        del fields["question_0_correct_option"]
        response = self.client.post(_apply_url(), data=fields)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Выберите правильный ответ.", response.text)

    def test_validation_failure_does_not_modify_quiz(self) -> None:
        before = self.quiz_path.read_text(encoding="utf-8")
        preview_id = self._preview_id()
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"text": ""}},
            ),
        )
        self.assertEqual(self.quiz_path.read_text(encoding="utf-8"), before)

    def test_validation_failure_does_not_consume_preview(self) -> None:
        preview_id = self._preview_id()
        self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={0: {"text": ""}},
            ),
        )
        self.assertIsNotNone(self.preview_store.get(preview_id))

    def test_validation_failure_preserves_edited_text(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={
                    0: {
                        "text": "Preserved edited text",
                        "options": {"b": ""},
                    }
                },
            ),
        )
        self.assertIn("Preserved edited text", response.text)

    def test_validation_failure_preserves_checkbox_selection(self) -> None:
        preview_id = self._preview_id()
        fields = _apply_form_data(
            preview_id,
            selected=["1"],
            question_edits={1: {"text": ""}},
        )
        response = self.client.post(_apply_url(), data=fields)
        self.assertIn('value="1"', response.text)
        checked_boxes = re.findall(
            r'name="selected_questions"[^>]*checked',
            response.text,
        )
        self.assertEqual(len(checked_boxes), 1)

    def test_validation_failure_preserves_chosen_correct_answer(self) -> None:
        preview_id = self._preview_id()
        response = self.client.post(
            _apply_url(),
            data=_apply_form_data(
                preview_id,
                selected=["0"],
                question_edits={
                    0: {
                        "correct": "c",
                        "options": {"c": ""},
                    }
                },
            ),
        )
        self.assertIn('name="question_0_correct_option"', response.text)
        self.assertIn('value="c"', response.text)


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
                _apply_request("not-valid")
            )


if __name__ == "__main__":
    unittest.main()
