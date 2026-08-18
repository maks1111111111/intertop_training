"""Tests for admin lesson editing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.content.runtime import ContentRuntime
from app.web.admin_lesson_edit_service import (
    AdminLessonEditError,
    AdminLessonEditRequest,
    AdminLessonEditService,
    _parse_multiline_list,
    _resolve_lesson_json_path,
)
from tests.web.test_web_ui import _authenticate_test_web_user
from tests.web.test_web_ui import _create_test_app, _write_course, _write_multi_lesson_course


def _write_lesson_with_quality_fields(
    courses_dir: Path,
    slug: str = "quality-course",
    lesson_id: str = "lesson_01",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir(exist_ok=True)
    if not (course_dir / "course.json").is_file():
        (course_dir / "course.json").write_text(
            json.dumps(
                {
                    "title": "Quality Course",
                    "description": "Course description",
                    "status": "published",
                    "language": "ru",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    lesson_dir = course_dir / lesson_id
    lesson_dir.mkdir(exist_ok=True)
    (lesson_dir / "lesson.json").write_text(
        json.dumps(
            {
                "title": "Quality lesson",
                "order": 1,
                "description": "Lesson body.",
                "practical_task": "Do the task.",
                "checklist": ["Step one", "Step two"],
                "common_mistakes": ["Mistake one"],
                "key_takeaways": ["Takeaway one"],
                "application_tips": ["Tip one"],
                "custom_future_field": {"x": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_lesson_with_structured_task(
    courses_dir: Path,
    slug: str = "structured-course",
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": "Structured Course",
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
                "title": "Structured lesson",
                "order": 1,
                "description": "Body.",
                "practical_task": "",
                "structured_practical_task": {
                    "title": "Structured title",
                    "description": "Structured description",
                    "expected_result": "Expected result",
                    "estimated_minutes": 20,
                },
                "checklist": ["Item one"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_course_with_quiz(courses_dir: Path, slug: str = "quiz-course") -> None:
    _write_course(courses_dir, slug, title="Quiz Course")
    quiz = {
        "id": f"{slug}_quiz",
        "title": "Итоговый тест",
        "passing_score": 80,
        "randomize_options": False,
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Question?",
                "options": [
                    {"id": "a", "text": "Wrong"},
                    {"id": "b", "text": "Right"},
                ],
                "correct_option_ids": ["b"],
            }
        ],
    }
    (courses_dir / slug / "quiz.json").write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class AdminLessonEditPageTests(unittest.TestCase):
    """Verify admin lesson edit HTTP endpoints."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            self.courses_dir
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_get_edit_page_returns_200_for_existing_lesson(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/quality-course/lessons/lesson_01/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Редактирование урока", response.text)

    def test_edit_page_prefills_form_fields(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/quality-course/lessons/lesson_01/edit")
        html = response.text

        self.assertIn("Quality lesson", html)
        self.assertIn("Lesson body.", html)
        self.assertIn("Do the task.", html)
        self.assertIn("Step one", html)
        self.assertIn("Takeaway one", html)
        self.assertIn("Tip one", html)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.get("/admin/courses/missing/lessons/lesson_01/edit")

        self.assertEqual(response.status_code, 404)

    def test_unknown_lesson_returns_404(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha/lessons/lesson_99/edit")

        self.assertEqual(response.status_code, 404)

    def test_post_valid_edit_redirects(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Updated body.",
                "practical_task": "Updated task.",
                "checklist": "Check A\nCheck B",
                "key_takeaways": "Key A",
                "application_tips": "Tip A\nTip B",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/courses/quality-course")

    def test_title_persists(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["title"], "Updated lesson")

    def test_description_persists(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Quality lesson",
                "description": "Updated body text.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["description"], "Updated body text.")

    def test_practical_task_persists(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Quality lesson",
                "description": "Body.",
                "practical_task": "New practical task.",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["practical_task"], "New practical task.")

    def test_checklist_persists_as_list(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Quality lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "Alpha\n\nBeta\n",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["checklist"], ["Alpha", "Beta"])

    def test_key_takeaways_persist(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Quality lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "One\nTwo",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["key_takeaways"], ["One", "Two"])

    def test_application_tips_persist(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Quality lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "Tip A",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["application_tips"], ["Tip A"])

    def test_lesson_order_is_preserved(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["order"], 1)

    def test_unknown_fields_are_preserved(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["custom_future_field"], {"x": 1})

    def test_common_mistakes_are_preserved(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (self.courses_dir / "quality-course" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["common_mistakes"], ["Mistake one"])

    def test_structured_practical_task_is_preserved(self) -> None:
        _write_lesson_with_structured_task(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/structured-course/lessons/lesson_01/edit",
            data={
                "title": "Updated structured lesson",
                "description": "Updated body.",
                "practical_task": "",
                "checklist": "New item",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_json = json.loads(
            (
                self.courses_dir / "structured-course" / "lesson_01" / "lesson.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(lesson_json["title"], "Updated structured lesson")
        self.assertEqual(
            lesson_json["structured_practical_task"],
            {
                "title": "Structured title",
                "description": "Structured description",
                "expected_result": "Expected result",
                "estimated_minutes": 20,
            },
        )

    def test_course_json_is_untouched(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()
        course_json_before = (
            self.courses_dir / "quality-course" / "course.json"
        ).read_text(encoding="utf-8")

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        course_json_after = (
            self.courses_dir / "quality-course" / "course.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(course_json_before, course_json_after)

    def test_quiz_json_is_untouched(self) -> None:
        _write_course_with_quiz(self.courses_dir, "quiz-course")
        self.app.state.content_runtime.refresh()
        quiz_before = (self.courses_dir / "quiz-course" / "quiz.json").read_text(
            encoding="utf-8"
        )

        self.client.post(
            "/admin/courses/quiz-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        quiz_after = (self.courses_dir / "quiz-course" / "quiz.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(quiz_before, quiz_after)

    def test_other_lesson_files_are_untouched(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime.refresh()
        lesson_two_before = (
            self.courses_dir / "alpha" / "lesson_02" / "lesson.json"
        ).read_text(encoding="utf-8")

        self.client.post(
            "/admin/courses/alpha/lessons/lesson_01/edit",
            data={
                "title": "Updated first",
                "description": "Updated body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        lesson_two_after = (
            self.courses_dir / "alpha" / "lesson_02" / "lesson.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(lesson_two_before, lesson_two_after)

    def test_invalid_empty_title_is_rejected(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "   ",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Название урока обязательно.", response.text)

    def test_no_absolute_paths_in_html(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/quality-course/lessons/lesson_01/edit")

        self.assertNotIn(str(self.courses_dir.resolve()), response.text)

    def test_admin_detail_has_edit_link(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/quality-course")

        self.assertIn(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            response.text,
        )

    @patch("app.web.admin_lesson_edit_service.RuntimeRefreshService.refresh")
    def test_runtime_refresh_called_after_success(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        mock_refresh.assert_called_once()

    @patch("app.web.admin_lesson_edit_service.RuntimeRefreshService.refresh")
    def test_runtime_refresh_not_called_after_validation_failure(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        mock_refresh.assert_not_called()

    @patch("app.web.admin_lesson_edit_service.RuntimeRefreshService.refresh")
    def test_malformed_lesson_json_returns_safe_error(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()
        lesson_json = self.courses_dir / "quality-course" / "lesson_01" / "lesson.json"
        malformed = "{not valid json"
        lesson_json.write_text(malformed, encoding="utf-8")

        with patch.object(self.app.state.content_runtime, "_ensure_fresh"):
            response = self.client.post(
                "/admin/courses/quality-course/lessons/lesson_01/edit",
                data={
                    "title": "Updated lesson",
                    "description": "Body.",
                    "practical_task": "",
                    "checklist": "",
                    "key_takeaways": "",
                    "application_tips": "",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить данные урока.", response.text)
        self.assertEqual(lesson_json.read_text(encoding="utf-8"), malformed)
        mock_refresh.assert_not_called()

    @patch("app.web.admin_lesson_edit_service.RuntimeRefreshService.refresh")
    def test_unreadable_lesson_json_returns_safe_error(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()
        lesson_json = self.courses_dir / "quality-course" / "lesson_01" / "lesson.json"

        with patch.object(
            Path,
            "read_text",
            side_effect=OSError("permission denied"),
        ):
            response = self.client.post(
                "/admin/courses/quality-course/lessons/lesson_01/edit",
                data={
                    "title": "Updated lesson",
                    "description": "Body.",
                    "practical_task": "",
                    "checklist": "",
                    "key_takeaways": "",
                    "application_tips": "",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось загрузить данные урока.", response.text)
        mock_refresh.assert_not_called()
        self.assertTrue(lesson_json.is_file())

    @patch("app.web.admin_lesson_edit_service._atomic_write_json")
    @patch("app.web.admin_lesson_edit_service.RuntimeRefreshService.refresh")
    def test_write_failure_returns_safe_error(
        self,
        mock_refresh: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()
        mock_write.side_effect = OSError("disk full")

        response = self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Updated lesson",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сохранить изменения", response.text)
        mock_refresh.assert_not_called()

    def test_student_lesson_reflects_updated_content(self) -> None:
        _authenticate_test_web_user(self.client.app)
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Student visible title",
                "description": "Student visible body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        response = self.client.get("/courses/quality-course/lessons/lesson_01")
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("Student visible title", html)
        self.assertIn("Student visible body.", html)

    def test_admin_detail_reflects_updated_lesson_title(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post(
            "/admin/courses/quality-course/lessons/lesson_01/edit",
            data={
                "title": "Admin detail title",
                "description": "Body.",
                "practical_task": "",
                "checklist": "",
                "key_takeaways": "",
                "application_tips": "",
            },
        )

        response = self.client.get("/admin/courses/quality-course")

        self.assertIn("Admin detail title", response.text)


class AdminLessonEditServiceTests(unittest.TestCase):
    """Direct tests for admin lesson edit service behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        self.runtime = ContentRuntime(self.courses_dir)
        self.service = AdminLessonEditService(self.courses_dir, self.runtime)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_traversal_like_slug_is_rejected(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.runtime.refresh()

        with self.assertRaises(AdminLessonEditError):
            self.service.update_lesson(
                AdminLessonEditRequest(
                    slug="../quality-course",
                    lesson_id="lesson_01",
                    title="Bad",
                    description="",
                    practical_task="",
                    checklist=[],
                    key_takeaways=[],
                    application_tips=[],
                )
            )

    def test_traversal_like_lesson_id_is_rejected(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        self.runtime.refresh()

        with self.assertRaises(AdminLessonEditError):
            self.service.update_lesson(
                AdminLessonEditRequest(
                    slug="quality-course",
                    lesson_id="../lesson_01",
                    title="Bad",
                    description="",
                    practical_task="",
                    checklist=[],
                    key_takeaways=[],
                    application_tips=[],
                )
            )

    def test_editing_one_course_does_not_modify_another(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir, slug="course-a")
        _write_lesson_with_quality_fields(
            self.courses_dir,
            slug="course-b",
            lesson_id="lesson_01",
        )
        self.runtime.refresh()

        self.service.update_lesson(
            AdminLessonEditRequest(
                slug="course-a",
                lesson_id="lesson_01",
                title="Only A updated",
                description="Body A.",
                practical_task="",
                checklist=[],
                key_takeaways=[],
                application_tips=[],
            )
        )

        lesson_b = json.loads(
            (self.courses_dir / "course-b" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_b["title"], "Quality lesson")

    def test_parse_multiline_list_strips_empty_lines(self) -> None:
        self.assertEqual(_parse_multiline_list(" one \n\n two \n"), ["one", "two"])

    def test_resolve_lesson_json_path_rejects_outside_destination(self) -> None:
        _write_lesson_with_quality_fields(self.courses_dir)
        other_dir = self.courses_dir / "other"
        other_dir.mkdir()
        (other_dir / "lesson.json").write_text("{}", encoding="utf-8")

        with self.assertRaises(AdminLessonEditError):
            _resolve_lesson_json_path(self.courses_dir, "quality-course", "../other")


if __name__ == "__main__":
    unittest.main()
