"""Tests for admin AI lesson question preview generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ai.quiz_interfaces import (
    GeneratedQuiz,
    QuizGenerationResult,
    QuizOption,
    QuizQuestion,
)
from app.ai.quiz_service import QuizGenerationService
from app.content.runtime import ContentRuntime
from app.web.admin_lesson_question_preview_service import (
    AdminLessonQuestionPreviewError,
    AdminLessonQuestionPreviewService,
)
from tests.web.test_web_ui import (
    _create_test_app,
    _write_course,
    _write_course_with_quiz,
    _write_multi_lesson_course,
)


def _preview_url(slug: str = "alpha", lesson_id: str = "lesson_01") -> str:
    return f"/admin/courses/{slug}/lessons/{lesson_id}/generate-questions"


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
                "description": "Unique lesson body for preview generation.",
                "practical_task": "Practice task text.",
                "checklist": ["Item one"],
                "key_takeaways": ["Takeaway one"],
                "application_tips": ["Tip one"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _mock_quiz_result() -> QuizGenerationResult:
    return QuizGenerationResult(
        quiz=GeneratedQuiz(
            title="Preview Quiz",
            passing_score=80,
            questions=(
                QuizQuestion(
                    id="q1",
                    lesson="lesson_01",
                    question="What is the main topic?",
                    options=(
                        QuizOption(id="a", text="Wrong answer", correct=False),
                        QuizOption(id="b", text="Correct answer", correct=True),
                        QuizOption(id="c", text="Another wrong", correct=False),
                        QuizOption(id="d", text="Yet another wrong", correct=False),
                    ),
                ),
                QuizQuestion(
                    id="q2",
                    lesson="lesson_01",
                    question="Second preview question?",
                    options=(
                        QuizOption(id="a", text="Option A", correct=True),
                        QuizOption(id="b", text="Option B", correct=False),
                        QuizOption(id="c", text="Option C", correct=False),
                        QuizOption(id="d", text="Option D", correct=False),
                    ),
                ),
            ),
        )
    )


def _create_client_with_mock(
    courses_dir: Path,
) -> tuple[TestClient, MagicMock, tempfile.TemporaryDirectory, tempfile.TemporaryDirectory]:
    app, db_tmp, db_path, upload_tmp = _create_test_app(courses_dir)
    mock_quiz_service = MagicMock(spec=QuizGenerationService)
    mock_quiz_service.generate_quiz.return_value = _mock_quiz_result()
    app.state.admin_lesson_question_preview_service = AdminLessonQuestionPreviewService(
        app.state.content_runtime,
        quiz_generation_service=mock_quiz_service,
    )
    client = TestClient(app)
    return client, mock_quiz_service, db_tmp, upload_tmp


class AdminLessonQuestionPreviewGetTests(unittest.TestCase):
    """Verify admin lesson question preview GET endpoints."""

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

    def test_page_contains_warning(self) -> None:
        response = self.client.get(_preview_url())
        self.assertIn(
            "Вопросы будут только сгенерированы для предварительного просмотра.",
            response.text,
        )
        self.assertIn("Курс изменен не будет.", response.text)

    def test_page_contains_course_and_lesson_titles(self) -> None:
        response = self.client.get(_preview_url())
        self.assertIn("Alpha Course", response.text)
        self.assertIn("First lesson", response.text)

    def test_page_contains_generate_button(self) -> None:
        response = self.client.get(_preview_url())
        self.assertIn("Сгенерировать", response.text)

    def test_lesson_edit_page_contains_ai_button(self) -> None:
        response = self.client.get("/admin/courses/alpha/lessons/lesson_01/edit")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Сгенерировать вопросы AI", response.text)
        self.assertIn("/generate-questions", response.text)

    def test_unknown_course_returns_404(self) -> None:
        response = self.client.get(_preview_url("missing-course"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_unknown_lesson_returns_404(self) -> None:
        response = self.client.get(_preview_url(lesson_id="missing-lesson"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Урок не найден", response.text)

    def test_no_filesystem_path_in_html(self) -> None:
        response = self.client.get(_preview_url())
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)


class AdminLessonQuestionPreviewPostTests(unittest.TestCase):
    """Verify admin lesson question preview POST behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        (
            self.client,
            self.mock_quiz_service,
            self.db_tmp,
            self.upload_tmp,
        ) = _create_client_with_mock(self.courses_dir)

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_post_returns_200(self) -> None:
        response = self.client.post(_preview_url())
        self.assertEqual(response.status_code, 200)

    def test_ai_is_called(self) -> None:
        self.client.post(_preview_url())
        self.mock_quiz_service.generate_quiz.assert_called_once()

    def test_uses_only_selected_lesson_content(self) -> None:
        _write_multi_lesson_course(self.courses_dir, slug="multi")
        runtime = ContentRuntime(self.courses_dir)
        mock_quiz_service = MagicMock(spec=QuizGenerationService)
        mock_quiz_service.generate_quiz.return_value = _mock_quiz_result()
        service = AdminLessonQuestionPreviewService(
            runtime,
            quiz_generation_service=mock_quiz_service,
        )
        service.generate_preview("multi", "lesson_02")

        request = mock_quiz_service.generate_quiz.call_args.args[0]
        self.assertEqual(len(request.lessons), 1)
        self.assertEqual(request.lessons[0].title, "Second lesson")
        self.assertEqual(request.lessons[0].content, "Body text.")

    def test_preview_displays_questions(self) -> None:
        response = self.client.post(_preview_url())
        self.assertIn("Предпросмотр вопросов", response.text)
        self.assertIn("What is the main topic?", response.text)
        self.assertIn("Correct answer", response.text)
        self.assertIn("Правильный ответ", response.text)
        self.assertIn("Second preview question?", response.text)

    def test_quiz_json_unchanged(self) -> None:
        _write_course_with_quiz(self.courses_dir, "quiz-course")
        quiz_path = self.courses_dir / "quiz-course" / "quiz.json"
        before = quiz_path.read_text(encoding="utf-8")
        self.client.post(_preview_url("quiz-course"))
        self.assertEqual(quiz_path.read_text(encoding="utf-8"), before)

    def test_lesson_json_unchanged(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        before = lesson_path.read_text(encoding="utf-8")
        self.client.post(_preview_url())
        self.assertEqual(lesson_path.read_text(encoding="utf-8"), before)

    def test_course_json_unchanged(self) -> None:
        course_path = self.courses_dir / "alpha" / "course.json"
        before = course_path.read_text(encoding="utf-8")
        self.client.post(_preview_url())
        self.assertEqual(course_path.read_text(encoding="utf-8"), before)

    def test_runtime_refresh_not_called(self) -> None:
        with patch(
            "app.services.runtime_refresh_service.RuntimeRefreshService.refresh"
        ) as mock_refresh:
            self.client.post(_preview_url())
        mock_refresh.assert_not_called()

    def test_ai_error_shows_safe_message(self) -> None:
        self.mock_quiz_service.generate_quiz.side_effect = ValueError("provider failure")
        response = self.client.post(_preview_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось сгенерировать вопросы.", response.text)
        self.assertNotIn("provider failure", response.text)
        self.assertNotIn("Traceback", response.text)

    def test_unknown_course_post_returns_404(self) -> None:
        response = self.client.post(_preview_url("missing-course"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Курс не найден", response.text)

    def test_unknown_lesson_post_returns_404(self) -> None:
        response = self.client.post(_preview_url(lesson_id="missing-lesson"))
        self.assertEqual(response.status_code, 404)
        self.assertIn("Урок не найден", response.text)

    def test_no_filesystem_path_in_error_html(self) -> None:
        self.mock_quiz_service.generate_quiz.side_effect = RuntimeError("boom")
        response = self.client.post(_preview_url())
        self.assertNotIn(str(self.courses_dir.resolve()), response.text)


class AdminLessonQuestionPreviewServiceTests(unittest.TestCase):
    """Direct unit tests for preview service behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_rich_lesson_course(self.courses_dir)
        self.runtime = ContentRuntime(self.courses_dir)
        self.mock_quiz_service = MagicMock(spec=QuizGenerationService)
        self.mock_quiz_service.generate_quiz.return_value = _mock_quiz_result()
        self.service = AdminLessonQuestionPreviewService(
            self.runtime,
            quiz_generation_service=self.mock_quiz_service,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_malformed_lesson_returns_none_for_preview_page(self) -> None:
        lesson_path = self.courses_dir / "alpha" / "lesson_01" / "lesson.json"
        lesson_path.write_text("{not-json", encoding="utf-8")
        runtime = ContentRuntime(self.courses_dir)
        service = AdminLessonQuestionPreviewService(
            runtime,
            quiz_generation_service=self.mock_quiz_service,
        )
        self.assertIsNone(service.get_preview_page("alpha", "lesson_01"))
        self.assertEqual(service.get_not_found_reason("alpha", "lesson_01"), "lesson")

    def test_traversal_like_slug_rejected(self) -> None:
        self.assertIsNone(self.service.get_preview_page("../alpha", "lesson_01"))
        self.assertEqual(
            self.service.get_not_found_reason("../alpha", "lesson_01"),
            "course",
        )

    def test_traversal_like_lesson_id_rejected(self) -> None:
        self.assertIsNone(self.service.get_preview_page("alpha", "../lesson_01"))
        self.assertEqual(
            self.service.get_not_found_reason("alpha", "../lesson_01"),
            "lesson",
        )

    def test_generate_preview_maps_difficulty_and_tags_defaults(self) -> None:
        preview = self.service.generate_preview("alpha", "lesson_01")
        self.assertTrue(preview.generated)
        self.assertEqual(len(preview.questions), 2)
        self.assertEqual(preview.questions[0].difficulty, 1)
        self.assertEqual(preview.questions[0].tags, ())

    def test_generate_preview_raises_for_missing_lesson(self) -> None:
        with self.assertRaises(AdminLessonQuestionPreviewError):
            self.service.generate_preview("alpha", "missing-lesson")


class AdminLessonQuestionPreviewRegressionTests(unittest.TestCase):
    """Regression checks for unrelated admin and student routes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_course(self.courses_dir, "alpha", title="Alpha Course")
        self.client, _, self.db_tmp, self.upload_tmp = _create_client_with_mock(
            self.courses_dir
        )

    def tearDown(self) -> None:
        self.upload_tmp.cleanup()
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_admin_dashboard_still_works(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)

    def test_student_course_page_still_works(self) -> None:
        response = self.client.get("/courses/alpha")
        self.assertEqual(response.status_code, 200)

    def test_lesson_edit_still_works(self) -> None:
        response = self.client.get("/admin/courses/alpha/lessons/lesson_01/edit")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
