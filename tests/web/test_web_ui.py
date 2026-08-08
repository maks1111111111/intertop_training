"""Tests for the read-only Web Learning UI."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.content.runtime import ContentRuntime
from app.database.db import get_connection, initialize_database
from app.web.progress_service import WEB_DEMO_USER_ID, WebProgressService


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


def _write_multi_lesson_course(courses_dir: Path, slug: str = "alpha") -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        '{"title": "Alpha Course", "status": "published", "language": "ru"}',
        encoding="utf-8",
    )
    for lesson_slug, title, order in (
        ("lesson_01", "First lesson", 1),
        ("lesson_02", "Second lesson", 2),
        ("lesson_03", "Third lesson", 3),
    ):
        lesson_dir = course_dir / lesson_slug
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            (
                '{"title": "'
                + title
                + '", "order": '
                + str(order)
                + ', "description": "Body text."}'
            ),
            encoding="utf-8",
        )


def _write_quiz_json(
    course_dir: Path,
    slug: str,
    *,
    passing_score: int = 80,
) -> None:
    quiz = {
        "id": f"{slug}_quiz",
        "title": "Итоговый тест",
        "passing_score": passing_score,
        "randomize_options": False,
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "First question?",
                "options": [
                    {"id": "a", "text": "Wrong one"},
                    {"id": "b", "text": "Right one"},
                ],
                "correct_option_ids": ["b"],
            },
            {
                "id": "q2",
                "type": "single_choice",
                "text": "Second question?",
                "options": [
                    {"id": "c", "text": "Also wrong"},
                    {"id": "d", "text": "Also right"},
                ],
                "correct_option_ids": ["d"],
            },
        ],
    }
    (course_dir / "quiz.json").write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_course_with_quiz(
    courses_dir: Path,
    slug: str = "quiz-course",
    *,
    passing_score: int = 80,
) -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        (
            '{"title": "Quiz Course", "description": "Course with final quiz.", '
            '"status": "published", "language": "ru"}'
        ),
        encoding="utf-8",
    )
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        '{"title": "Only lesson", "order": 1, "description": "Body text."}',
        encoding="utf-8",
    )
    _write_quiz_json(course_dir, slug, passing_score=passing_score)


def _write_empty_course(courses_dir: Path, slug: str = "empty") -> None:
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        '{"title": "Empty Course", "status": "published", "language": "ru"}',
        encoding="utf-8",
    )


def _create_test_app(courses_dir: Path) -> tuple:
    """Return app, temp db directory handle, and db path for isolated tests."""
    db_tmp = tempfile.TemporaryDirectory()
    db_path = Path(db_tmp.name) / "test.db"
    initialize_database(db_path)
    app = create_app()
    app.state.db_path = db_path
    app.state.content_runtime = ContentRuntime(courses_dir)
    return app, db_tmp, db_path


class WebUiTests(unittest.TestCase):
    """Verify server-rendered learning pages."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_course(self.courses_dir, "alpha", title="Alpha Course", language="ru")

        self.app, self.db_tmp, self.db_path = _create_test_app(self.courses_dir)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_root_redirects_to_courses(self) -> None:
        response = self.client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/courses")

    def test_courses_page_returns_200(self) -> None:
        response = self.client.get("/courses")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_courses_page_marks_courses_nav_as_active(self) -> None:
        response = self.client.get("/courses")
        html = response.text

        self.assertIn('href="/courses" class="nav-link is-active"', html)
        self.assertIn("sidebar-nav", html)
        self.assertIn("Курсы", html)

    def test_courses_page_shows_course_title_description_and_link(self) -> None:
        response = self.client.get("/courses")
        html = response.text

        self.assertIn("Alpha Course", html)
        self.assertIn("Course overview for learners.", html)
        self.assertIn('href="/courses/alpha"', html)
        self.assertIn("Открыть курс", html)

    def test_course_detail_page_returns_200(self) -> None:
        response = self.client.get("/courses/alpha")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Alpha Course", html)
        self.assertIn("Course overview for learners.", html)
        self.assertIn("First lesson", html)
        self.assertIn('href="/courses/alpha/lessons/lesson_01"', html)

    def test_lesson_page_returns_200_and_content(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_01")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("First lesson", html)
        self.assertIn("Body text.", html)

    def test_lesson_page_shows_quality_sections_when_present(self) -> None:
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

        response = self.client.get("/courses/alpha/lessons/lesson_01")
        html = response.text

        self.assertIn("Практическое задание", html)
        self.assertIn("Inspect the work area.", html)
        self.assertIn("Чек-лист", html)
        self.assertIn("Wear PPE", html)
        self.assertIn("Типичные ошибки", html)
        self.assertIn("Skipping inspection", html)
        self.assertIn("Главное запомнить", html)
        self.assertIn("Safety first", html)
        self.assertIn("Советы по применению", html)
        self.assertIn("Apply the checklist daily", html)

    def test_lesson_page_hides_empty_quality_sections(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_01")
        html = response.text

        self.assertNotIn("Практическое задание", html)
        self.assertNotIn("Чек-лист", html)
        self.assertNotIn("Типичные ошибки", html)
        self.assertNotIn("Главное запомнить", html)
        self.assertNotIn("Советы по применению", html)

    def test_unknown_course_returns_html_404(self) -> None:
        response = self.client.get("/courses/missing")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Курс не найден", response.text)
        self.assertIn(
            "Запрошенный курс недоступен или не существует.",
            response.text,
        )
        self.assertNotIn('"course_not_found"', response.text)

    def test_unknown_lesson_returns_html_404(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_99")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Урок не найден", response.text)
        self.assertIn(
            "Запрошенный урок недоступен или не существует.",
            response.text,
        )
        self.assertNotIn('"lesson_not_found"', response.text)

    def test_api_courses_endpoint_still_works(self) -> None:
        response = self.client.get("/api/v1/courses")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["slug"], "alpha")

    def test_single_lesson_shows_complete_course_only(self) -> None:
        response = self.client.get("/courses/alpha/lessons/lesson_01")
        html = response.text

        self.assertNotIn("← Предыдущий урок", html)
        self.assertNotIn("Следующий урок →", html)
        self.assertIn("✓ Завершить курс", html)

    def test_lesson_navigation_for_multi_lesson_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_multi_lesson_course(courses_dir, "nav-course")
            app, db_tmp, _db_path = _create_test_app(courses_dir)
            client = TestClient(app)

            first = client.get("/courses/nav-course/lessons/lesson_01")
            middle = client.get("/courses/nav-course/lessons/lesson_02")
            last = client.get("/courses/nav-course/lessons/lesson_03")
            db_tmp.cleanup()

        first_html = first.text
        middle_html = middle.text
        last_html = last.text

        self.assertNotIn("← Предыдущий урок", first_html)
        self.assertIn('href="/courses/nav-course/lessons/lesson_02"', first_html)
        self.assertIn("Следующий урок →", first_html)
        self.assertNotIn("✓ Завершить курс", first_html)

        self.assertIn('href="/courses/nav-course/lessons/lesson_01"', middle_html)
        self.assertIn("← Предыдущий урок", middle_html)
        self.assertIn('href="/courses/nav-course/lessons/lesson_03"', middle_html)
        self.assertIn("Следующий урок →", middle_html)
        self.assertNotIn("✓ Завершить курс", middle_html)

        self.assertIn('href="/courses/nav-course/lessons/lesson_02"', last_html)
        self.assertIn("← Предыдущий урок", last_html)
        self.assertNotIn("Следующий урок →", last_html)
        self.assertIn("✓ Завершить курс", last_html)


class WebProgressUiTests(unittest.TestCase):
    """Verify Web UI progress tracking and lesson statuses."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_multi_lesson_course(self.courses_dir, "progress-course")
        self.app, self.db_tmp, self.db_path = _create_test_app(self.courses_dir)
        self.client = TestClient(self.app)
        self.progress = WebProgressService(self.db_path)

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_course_page_shows_progress_block(self) -> None:
        response = self.client.get("/courses/progress-course")
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("Прогресс", html)
        self.assertIn("0 из 3 уроков", html)
        self.assertIn("0%", html)

    def test_course_page_shows_lesson_status_labels(self) -> None:
        response = self.client.get("/courses/progress-course")
        html = response.text

        self.assertIn("lesson-status--current", html)
        self.assertIn("Текущий", html)
        self.assertIn("lesson-status--not_started", html)
        self.assertIn("Не открыт", html)

    def test_opening_lesson_marks_it_completed(self) -> None:
        response = self.client.get("/courses/progress-course/lessons/lesson_01")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.progress.is_lesson_completed("progress-course", "lesson_01")
        )

    def test_reopening_lesson_does_not_create_duplicate(self) -> None:
        self.client.get("/courses/progress-course/lessons/lesson_01")
        self.client.get("/courses/progress-course/lessons/lesson_01")

        with get_connection(self.db_path) as connection:
            row_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM web_lesson_progress
                WHERE user_id = ? AND course_slug = ? AND lesson_id = ?
                """,
                (WEB_DEMO_USER_ID, "progress-course", "lesson_01"),
            ).fetchone()[0]
        self.assertEqual(row_count, 1)

    def test_course_page_updates_after_lesson_visit(self) -> None:
        self.client.get("/courses/progress-course/lessons/lesson_01")
        response = self.client.get("/courses/progress-course")
        html = response.text

        self.assertIn("1 из 3 уроков", html)
        self.assertIn("33%", html)
        self.assertIn("lesson-status--completed", html)
        self.assertIn("Завершён", html)
        self.assertIn("lesson-status--current", html)

    def test_completed_course_without_quiz_shows_message(self) -> None:
        for lesson_id in ("lesson_01", "lesson_02", "lesson_03"):
            self.client.get(f"/courses/progress-course/lessons/{lesson_id}")

        response = self.client.get("/courses/progress-course")
        html = response.text

        self.assertIn("100%", html)
        self.assertIn("3 из 3 уроков", html)
        self.assertIn("Курс завершён", html)

    def test_completed_course_with_quiz_shows_test_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_multi_lesson_course(courses_dir, "quiz-progress")
            _write_quiz_json(courses_dir / "quiz-progress", "quiz-progress")
            app, db_tmp, _db_path = _create_test_app(courses_dir)
            client = TestClient(app)

            for lesson_id in ("lesson_01", "lesson_02", "lesson_03"):
                client.get(f"/courses/quiz-progress/lessons/{lesson_id}")

            response = client.get("/courses/quiz-progress")
            html = response.text

            self.assertIn("Можно пройти итоговый тест", html)
            self.assertIn("Итоговый тест", html)
            db_tmp.cleanup()

    def test_single_lesson_course_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_course(courses_dir, "solo", title="Solo Course")
            app, db_tmp, db_path = _create_test_app(courses_dir)
            client = TestClient(app)
            progress = WebProgressService(db_path)

            before = client.get("/courses/solo")
            self.assertIn("Текущий", before.text)
            self.assertIn("0 из 1 уроков", before.text)

            client.get("/courses/solo/lessons/lesson_01")

            after = client.get("/courses/solo")
            self.assertIn("1 из 1 уроков", after.text)
            self.assertIn("100%", after.text)
            self.assertIn("Курс завершён", after.text)
            self.assertTrue(progress.is_lesson_completed("solo", "lesson_01"))
            db_tmp.cleanup()

    def test_course_without_lessons_has_no_progress_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_empty_course(courses_dir, "empty")
            app, db_tmp, _db_path = _create_test_app(courses_dir)
            client = TestClient(app)

            response = client.get("/courses/empty")
            html = response.text

            self.assertEqual(response.status_code, 200)
            self.assertNotIn("course-progress-percent", html)
            self.assertIn("В этом курсе пока нет уроков", html)
            db_tmp.cleanup()


class WebQuizUiTests(unittest.TestCase):
    """Verify read-only Web quiz flow."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.courses_dir = Path(self.tmp.name)
        _write_course(self.courses_dir, "plain", title="Plain Course")
        _write_course_with_quiz(self.courses_dir, "quiz-course")

        self.app, self.db_tmp, self.db_path = _create_test_app(self.courses_dir)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.db_tmp.cleanup()
        self.tmp.cleanup()

    def test_course_without_quiz_hides_quiz_block(self) -> None:
        response = self.client.get("/courses/plain")
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Итоговый тест", html)
        self.assertNotIn("/quiz", html)

    def test_course_with_quiz_shows_quiz_block(self) -> None:
        response = self.client.get("/courses/quiz-course")
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("Итоговый тест", html)
        self.assertIn("Вопросов: 2", html)
        self.assertIn("Проходной балл: 80%", html)
        self.assertIn('href="/courses/quiz-course/quiz"', html)
        self.assertIn("Начать тест", html)

    def test_quiz_get_page_returns_200(self) -> None:
        response = self.client.get("/courses/quiz-course/quiz")
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("Итоговый тест", html)
        self.assertIn("First question?", html)
        self.assertIn("Second question?", html)
        self.assertIn("Wrong one", html)
        self.assertIn("Right one", html)
        self.assertIn('name="answer_q1"', html)
        self.assertIn('name="answer_q2"', html)
        self.assertIn("Завершить тест", html)
        self.assertNotIn("correct_option_ids", html)
        self.assertNotIn('type="hidden"', html)

    def test_quiz_post_all_correct_passes(self) -> None:
        response = self.client.post(
            "/courses/quiz-course/quiz",
            data={"answer_q1": "b", "answer_q2": "d"},
        )
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("100%", html)
        self.assertIn("Правильных ответов: 2 из 2", html)
        self.assertIn("Тест пройден", html)
        self.assertNotIn("Тест не пройден", html)

    def test_quiz_post_all_wrong_fails(self) -> None:
        response = self.client.post(
            "/courses/quiz-course/quiz",
            data={"answer_q1": "a", "answer_q2": "c"},
        )
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("0%", html)
        self.assertIn("Правильных ответов: 0 из 2", html)
        self.assertIn("Тест не пройден", html)

    def test_quiz_post_unanswered_question_counts_as_wrong(self) -> None:
        response = self.client.post(
            "/courses/quiz-course/quiz",
            data={"answer_q1": "b"},
        )
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("50%", html)
        self.assertIn("Правильных ответов: 1 из 2", html)
        self.assertIn("Тест не пройден", html)
        self.assertIn("Ответ не выбран", html)

    def test_unknown_course_quiz_returns_html_404(self) -> None:
        response = self.client.get("/courses/missing/quiz")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Курс не найден", response.text)
        self.assertIn(
            "Запрошенный курс недоступен или не существует.",
            response.text,
        )
        self.assertNotIn('"course_not_found"', response.text)

    def test_course_without_quiz_returns_html_404(self) -> None:
        response = self.client.get("/courses/plain/quiz")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Тест недоступен", response.text)

    def test_fake_option_id_does_not_count_as_correct(self) -> None:
        response = self.client.post(
            "/courses/quiz-course/quiz",
            data={"answer_q1": "fake", "answer_q2": "d"},
        )
        html = response.text

        self.assertEqual(response.status_code, 200)
        self.assertIn("50%", html)
        self.assertIn("Правильных ответов: 1 из 2", html)
        self.assertIn("Тест не пройден", html)


if __name__ == "__main__":
    unittest.main()
