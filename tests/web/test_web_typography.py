"""Regression tests for application-wide Web typography consistency."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests.web.test_web_ui import _create_test_app

_CSS_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "css" / "app.css"
)


def _write_quiz_course(courses_dir: Path) -> None:
    course_dir = courses_dir / "typography-quiz"
    course_dir.mkdir()
    (course_dir / "course.json").write_text(
        '{"title": "Typography Quiz", "status": "published", "language": "ru"}',
        encoding="utf-8",
    )
    (course_dir / "quiz.json").write_text(
        (
            '{"id": "typography-quiz_quiz", "title": "Итоговый тест", '
            '"passing_score": 80, "version": 1, "randomize_questions": false, '
            '"randomize_options": false, "questions": ['
            '{"id": "q1", "type": "single_choice", "text": "Sample question?", '
            '"options": [{"id": "a", "text": "Option A"}, {"id": "b", "text": "Option B"}], '
            '"correct_option_ids": ["a"], "explanation": "", "lesson": "lesson_01", '
            '"difficulty": 1, "tags": []}'
            "]}"
        ),
        encoding="utf-8",
    )


class WebTypographyCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = _CSS_PATH.read_text(encoding="utf-8")

    def test_global_font_stack_defined_on_root(self) -> None:
        self.assertIn("--font-family-base", self.css)
        self.assertIn("font-family: var(--font-family-base)", self.css)

    def test_form_controls_inherit_application_font(self) -> None:
        self.assertRegex(
            self.css,
            r"button,\s*\ninput,\s*\nselect,\s*\ntextarea,\s*\noptgroup,\s*\noption\s*\{[^}]*font:\s*inherit",
            re.DOTALL,
        )

    def test_headings_inherit_application_font_weight_baseline(self) -> None:
        self.assertIn("h1,\nh2,\nh3,\nh4,\nh5,\nh6", self.css)
        self.assertIn("font-family: inherit", self.css)
        self.assertIn("font-weight: var(--font-weight-semibold)", self.css)

    def test_quiz_question_title_uses_semibold_not_browser_bold(self) -> None:
        self.assertRegex(
            self.css,
            r"\.quiz-question-title\s*\{[^}]*font-weight:\s*var\(--font-weight-semibold\)",
            re.DOTALL,
        )

    def test_quiz_option_text_uses_body_font_size(self) -> None:
        self.assertRegex(
            self.css,
            r"\.quiz-option-text\s*\{[^}]*font-size:\s*var\(--font-size-body\)",
            re.DOTALL,
        )

    def test_buttons_use_application_font(self) -> None:
        self.assertRegex(
            self.css,
            r"\.button\s*\{[^}]*font-family:\s*inherit",
            re.DOTALL,
        )


class WebTypographyPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        courses_dir = Path(self.tmp.name)
        _write_quiz_course(courses_dir)
        self.app, self.db_tmp, self.db_path, self.upload_tmp = _create_test_app(
            courses_dir
        )
        self.addCleanup(self.upload_tmp.cleanup)
        self.addCleanup(self.db_tmp.cleanup)
        self.client = TestClient(self.app)

    def test_quiz_page_links_application_stylesheet(self) -> None:
        response = self.client.get("/courses/typography-quiz/quiz")
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/css/app.css', response.text)

    def test_quiz_page_uses_shared_typography_classes(self) -> None:
        response = self.client.get("/courses/typography-quiz/quiz")
        html = response.text
        self.assertIn("quiz-header-title", html)
        self.assertIn("quiz-question-title", html)
        self.assertIn("quiz-option-text", html)
        self.assertIn("quiz-submit-btn", html)
        self.assertIn("Завершить тест", html)
        self.assertIn("Вернуться к курсу", html)


if __name__ == "__main__":
    unittest.main()
