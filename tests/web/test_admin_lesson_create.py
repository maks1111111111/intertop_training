"""Tests for admin lesson creation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.web.admin_lesson_create_service import (
    AdminLessonCreateError,
    AdminLessonCreateService,
    _next_lesson_id_and_order,
    _safe_remove_lesson_dir,
)
from tests.web.test_web_ui import _authenticate_test_web_user
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
    _write_empty_course,
    _write_multi_lesson_course,
)


def _write_course_with_gap_lessons(courses_dir: Path, slug: str = "gap-course") -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": "Gap Course",
                "status": "published",
                "language": "ru",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for lesson_id, title, order in (
        ("lesson_01", "First lesson", 1),
        ("lesson_02", "Second lesson", 2),
        ("lesson_05", "Fifth lesson", 5),
    ):
        lesson_dir = course_dir / lesson_id
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            json.dumps(
                {
                    "title": title,
                    "order": order,
                    "description": "Body.",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


class AdminLessonCreateServiceTests(unittest.TestCase):
    """Unit tests for lesson id/order selection and cleanup safety."""

    def test_next_lesson_id_for_empty_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp)
            (course_dir / "course.json").write_text("{}", encoding="utf-8")

            lesson_id, order = _next_lesson_id_and_order(course_dir)

            self.assertEqual(lesson_id, "lesson_01")
            self.assertEqual(order, 1)

    def test_next_lesson_id_uses_max_suffix_not_holes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp)
            for lesson_id, order in (("lesson_01", 1), ("lesson_02", 2), ("lesson_05", 5)):
                lesson_dir = course_dir / lesson_id
                lesson_dir.mkdir()
                (lesson_dir / "lesson.json").write_text(
                    json.dumps({"title": lesson_id, "order": order}),
                    encoding="utf-8",
                )

            lesson_id, order = _next_lesson_id_and_order(course_dir)

            self.assertEqual(lesson_id, "lesson_06")
            self.assertEqual(order, 6)

    def test_safe_remove_refuses_path_outside_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_dir = root / "course-a"
            other_dir = root / "other"
            course_dir.mkdir()
            other_dir.mkdir()

            _safe_remove_lesson_dir(course_dir, other_dir)

            self.assertTrue(other_dir.is_dir())


class AdminLessonCreatePageTests(unittest.TestCase):
    """Verify admin lesson creation HTTP endpoints."""

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

    def test_post_creates_new_lesson(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/alpha/lessons/create",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/alpha/lessons/lesson_02/edit",
        )
        self.assertTrue(
            (self.courses_dir / "alpha" / "lesson_02" / "lesson.json").is_file()
        )

    def test_first_lesson_becomes_lesson_01(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/empty/lessons/create",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/empty/lessons/lesson_01/edit",
        )
        self.assertTrue(
            (self.courses_dir / "empty" / "lesson_01" / "lesson.json").is_file()
        )

    def test_existing_lesson_01_and_02_produce_lesson_03(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/alpha/lessons/create",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/alpha/lessons/lesson_04/edit",
        )

    def test_gap_lessons_produce_next_suffix_not_reused_hole(self) -> None:
        _write_course_with_gap_lessons(self.courses_dir)
        self.app.state.content_runtime.refresh()

        response = self.client.post(
            "/admin/courses/gap-course/lessons/create",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/courses/gap-course/lessons/lesson_06/edit",
        )
        self.assertFalse((self.courses_dir / "gap-course" / "lesson_03").exists())
        self.assertFalse((self.courses_dir / "gap-course" / "lesson_04").exists())

    def test_new_order_is_max_existing_plus_one(self) -> None:
        _write_course_with_gap_lessons(self.courses_dir)
        self.app.state.content_runtime.refresh()

        self.client.post("/admin/courses/gap-course/lessons/create")

        lesson_json = json.loads(
            (
                self.courses_dir / "gap-course" / "lesson_06" / "lesson.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(lesson_json["order"], 6)

    def test_initial_lesson_json_contract(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()

        self.client.post("/admin/courses/empty/lessons/create")

        lesson_json = json.loads(
            (self.courses_dir / "empty" / "lesson_01" / "lesson.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lesson_json["title"], "Новый урок")
        self.assertEqual(lesson_json["order"], 1)
        self.assertEqual(lesson_json["description"], "")
        self.assertEqual(lesson_json["practical_task"], "")
        self.assertEqual(lesson_json["checklist"], [])
        self.assertEqual(lesson_json["common_mistakes"], [])
        self.assertEqual(lesson_json["key_takeaways"], [])
        self.assertEqual(lesson_json["application_tips"], [])

    def test_existing_lessons_unchanged(self) -> None:
        _write_multi_lesson_course(self.courses_dir, "alpha")
        self.app.state.content_runtime.refresh()
        before = (
            self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        ).read_text(encoding="utf-8")

        self.client.post("/admin/courses/alpha/lessons/create")

        after = (self.courses_dir / "alpha" / "lesson_01" / "lesson.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(before, after)

    def test_course_json_unchanged(self) -> None:
        _write_course_with_quiz(self.courses_dir, "quiz-course")
        self.app.state.content_runtime.refresh()
        before = (self.courses_dir / "quiz-course" / "course.json").read_text(
            encoding="utf-8"
        )

        self.client.post("/admin/courses/quiz-course/lessons/create")

        after = (self.courses_dir / "quiz-course" / "course.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(before, after)

    def test_quiz_json_unchanged(self) -> None:
        _write_course_with_quiz(self.courses_dir, "quiz-course")
        self.app.state.content_runtime.refresh()
        before = (self.courses_dir / "quiz-course" / "quiz.json").read_text(
            encoding="utf-8"
        )

        self.client.post("/admin/courses/quiz-course/lessons/create")

        after = (self.courses_dir / "quiz-course" / "quiz.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(before, after)

    def test_runtime_refresh_called_after_success(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()
        runtime = self.app.state.content_runtime
        with patch.object(runtime, "refresh", wraps=runtime.refresh) as refresh_mock:
            self.client.post("/admin/courses/alpha/lessons/create")
        refresh_mock.assert_called_once()

    def test_write_failure_removes_new_lesson_directory(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()
        runtime = self.app.state.content_runtime
        service = AdminLessonCreateService(self.courses_dir, runtime)

        with patch(
            "app.web.admin_lesson_create_service._atomic_write_json",
            side_effect=OSError("write failed"),
        ):
            with self.assertRaises(AdminLessonCreateError):
                service.create_lesson("empty")

        self.assertFalse((self.courses_dir / "empty" / "lesson_01").exists())

    def test_runtime_refresh_not_called_on_directory_creation_failure(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()
        runtime = self.app.state.content_runtime
        service = AdminLessonCreateService(self.courses_dir, runtime)

        with patch.object(Path, "mkdir", side_effect=OSError("mkdir failed")):
            with patch.object(runtime, "refresh") as refresh_mock:
                with self.assertRaises(AdminLessonCreateError):
                    service.create_lesson("empty")
        refresh_mock.assert_not_called()

    def test_runtime_refresh_not_called_on_write_failure(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()
        runtime = self.app.state.content_runtime
        service = AdminLessonCreateService(self.courses_dir, runtime)

        with patch(
            "app.web.admin_lesson_create_service._atomic_write_json",
            side_effect=OSError("write failed"),
        ):
            with patch.object(runtime, "refresh") as refresh_mock:
                with self.assertRaises(AdminLessonCreateError):
                    service.create_lesson("empty")
        refresh_mock.assert_not_called()

    def test_directory_creation_failure_returns_safe_error(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()

        with patch(
            "app.web.admin_lesson_create_service.AdminLessonCreateService.create_lesson",
            side_effect=AdminLessonCreateError("Не удалось создать урок. Попробуйте ещё раз."),
        ):
            response = self.client.post("/admin/courses/empty/lessons/create")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось создать урок", response.text)
        self.assertNotIn(str(self.courses_dir), response.text)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.post("/admin/courses/missing/lessons/create")

        self.assertEqual(response.status_code, 404)

    def test_traversal_like_slug_returns_safe_error(self) -> None:
        response = self.client.post("/admin/courses/../alpha/lessons/create")

        self.assertIn(response.status_code, {404, 400})

    def test_no_absolute_path_in_error_html(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()

        with patch(
            "app.web.admin_lesson_create_service._atomic_write_json",
            side_effect=OSError("write failed"),
        ):
            response = self.client.post("/admin/courses/empty/lessons/create")

        self.assertNotIn(str(self.courses_dir.resolve()), response.text)

    def test_new_lesson_appears_on_admin_course_detail(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        self.client.post("/admin/courses/alpha/lessons/create")

        response = self.client.get("/admin/courses/alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Новый урок", response.text)

    def test_new_lesson_appears_on_student_course_page(self) -> None:
        _authenticate_test_web_user(self.client.app)
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        self.client.post("/admin/courses/alpha/lessons/create")

        response = self.client.get("/courses/alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Новый урок", response.text)

    def test_new_lesson_edit_page_is_accessible(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()

        create_response = self.client.post(
            "/admin/courses/empty/lessons/create",
            follow_redirects=False,
        )
        edit_response = self.client.get(create_response.headers["location"])

        self.assertEqual(edit_response.status_code, 200)
        self.assertIn("Редактирование урока", edit_response.text)

    def test_repeated_creation_creates_sequential_lesson_ids(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()

        first = self.client.post(
            "/admin/courses/empty/lessons/create",
            follow_redirects=False,
        )
        self.assertEqual(first.headers["location"], "/admin/courses/empty/lessons/lesson_01/edit")

        second = self.client.post(
            "/admin/courses/empty/lessons/create",
            follow_redirects=False,
        )
        self.assertEqual(second.headers["location"], "/admin/courses/empty/lessons/lesson_02/edit")

    def test_admin_course_detail_contains_create_button(self) -> None:
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.app.state.content_runtime.refresh()

        response = self.client.get("/admin/courses/alpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Добавить урок", response.text)
        self.assertIn('/admin/courses/alpha/lessons/create', response.text)

    def test_runtime_refresh_failure_keeps_created_lesson(self) -> None:
        _write_empty_course(self.courses_dir, "empty")
        self.app.state.content_runtime.refresh()
        runtime = self.app.state.content_runtime
        service = AdminLessonCreateService(self.courses_dir, runtime)

        with patch(
            "app.web.admin_lesson_create_service.RuntimeRefreshService.refresh",
            side_effect=RuntimeError("refresh failed"),
        ):
            with self.assertRaises(AdminLessonCreateError):
                service.create_lesson("empty")

        self.assertTrue(
            (self.courses_dir / "empty" / "lesson_01" / "lesson.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
