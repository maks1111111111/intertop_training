"""Integration tests for scanner delegation to runtime_loader."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.content.runtime_loader import (
    Course,
    Lesson,
    Quiz,
    QuizOption,
    QuizQuestion,
)
from app.services import scanner
from app.services.scanner import get_course, scan_courses


def _write_minimal_course(
    courses_dir: Path,
    slug: str,
    *,
    course_order: int = 1,
    lesson_order: int = 1,
    with_quiz: bool = False,
    status: str = "published",
) -> Path:
    """Create a minimal valid published course directory."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "status": status,
                "order": course_order,
                "version": 2,
            }
        ),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "First lesson", "order": lesson_order}),
        encoding="utf-8",
    )

    if with_quiz:
        (course_dir / "quiz.json").write_text(
            json.dumps(
                {
                    "id": f"{slug}_quiz",
                    "title": "Test quiz",
                    "passing_score": 80,
                    "version": 1,
                    "randomize_questions": False,
                    "randomize_options": False,
                    "questions": [
                        {
                            "id": "q1",
                            "type": "single_choice",
                            "text": "Question one?",
                            "options": [
                                {"id": "a", "text": "Answer A"},
                                {"id": "b", "text": "Answer B"},
                            ],
                            "correct_option_ids": ["a"],
                            "explanation": "Because A.",
                            "lesson": "lesson_01",
                            "difficulty": 1,
                            "tags": ["tag1"],
                            "ai_context": "context",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    return course_dir


class ScannerRuntimeIntegrationTests(unittest.TestCase):
    """Verify scanner public API delegates to runtime_loader."""

    def test_scanner_reexports_runtime_loader_models(self) -> None:
        self.assertIs(scanner.Course, Course)
        self.assertIs(scanner.Lesson, Lesson)
        self.assertIs(scanner.Quiz, Quiz)
        self.assertIs(scanner.QuizOption, QuizOption)
        self.assertIs(scanner.QuizQuestion, QuizQuestion)

    def test_loads_valid_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            courses = scan_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        course = courses[0]
        self.assertEqual(course.slug, "alpha")
        self.assertEqual(course.title, "Title alpha")
        self.assertEqual(course.status, "published")
        self.assertEqual(course.version, 2)
        self.assertEqual(len(course.lessons), 1)
        self.assertEqual(course.lessons[0].title, "First lesson")

    def test_courses_are_sorted_by_order_then_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "z_course", course_order=2)
            _write_minimal_course(courses_dir, "a_course", course_order=1)

            courses = scan_courses(courses_dir)

        self.assertEqual([course.slug for course in courses], ["a_course", "z_course"])

    def test_courses_with_same_order_are_sorted_by_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "z_course", course_order=1)
            _write_minimal_course(courses_dir, "a_course", course_order=1)

            courses = scan_courses(courses_dir)

        self.assertEqual([course.slug for course in courses], ["a_course", "z_course"])

    def test_draft_course_is_not_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "draft_course", status="draft")

            courses = scan_courses(courses_dir)
            course = get_course(courses_dir, "draft_course")

        self.assertEqual(courses, [])
        self.assertIsNone(course)

    def test_nonexistent_base_dir_returns_empty_list_and_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = Path(tmp) / "missing"

        courses = scan_courses(missing_dir)
        course = get_course(missing_dir, "any")

        self.assertEqual(courses, [])
        self.assertIsNone(course)

    def test_lessons_are_sorted_by_order_then_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(
                courses_dir,
                "ordered",
                lesson_order=2,
            )

            lesson_b = course_dir / "lesson_b"
            lesson_b.mkdir()
            (lesson_b / "lesson.json").write_text(
                json.dumps({"title": "Lesson B", "order": 3}),
                encoding="utf-8",
            )

            lesson_a = course_dir / "lesson_a"
            lesson_a.mkdir()
            (lesson_a / "lesson.json").write_text(
                json.dumps({"title": "Lesson A", "order": 1}),
                encoding="utf-8",
            )

            course = get_course(courses_dir, "ordered")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(
            [lesson.path.name for lesson in course.lessons],
            ["lesson_a", "lesson_01", "lesson_b"],
        )

    def test_get_course_returns_matching_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "brands")

            course = get_course(courses_dir, "brands")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "brands")

    def test_get_course_returns_none_for_missing_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "brands")

            course = get_course(courses_dir, "missing")

        self.assertIsNone(course)

    def test_quiz_data_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "with_quiz", with_quiz=True)

            course = get_course(courses_dir, "with_quiz")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNotNone(course.quiz)
        quiz = course.quiz
        assert quiz is not None
        self.assertEqual(quiz.id, "with_quiz_quiz")
        self.assertEqual(quiz.title, "Test quiz")
        self.assertEqual(len(quiz.questions), 1)

        question = quiz.questions[0]
        self.assertEqual(question.id, "q1")
        self.assertEqual(question.text, "Question one?")
        self.assertEqual(question.correct_option_ids, ["a"])
        self.assertEqual(question.explanation, "Because A.")
        self.assertEqual(question.lesson, "lesson_01")
        self.assertEqual(question.tags, ["tag1"])
        self.assertEqual(question.ai_context, "context")
        self.assertEqual(len(question.options), 2)
        self.assertEqual(question.options[0].id, "a")

    def test_missing_course_json_does_not_block_other_courses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "good")

            broken_dir = courses_dir / "broken"
            broken_dir.mkdir()

            courses = scan_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "good")

    def test_works_with_absolute_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp).resolve()
            _write_minimal_course(courses_dir, "absolute")

            original_cwd = Path.cwd()
            try:
                os.chdir(Path("/tmp"))
                course = get_course(courses_dir, "absolute")
            finally:
                os.chdir(original_cwd)

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "absolute")


if __name__ == "__main__":
    unittest.main()
