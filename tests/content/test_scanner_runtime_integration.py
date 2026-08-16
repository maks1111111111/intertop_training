"""Integration tests for scanner delegation to runtime_loader."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content import runtime_loader
from app.content.runtime_loader import (
    Course,
    Lesson,
    Quiz,
    QuizOption,
    QuizQuestion,
    load_published_courses,
)
from app.services import scanner
from app.services.scanner import get_course, scan_courses


def _write_quiz(course_dir: Path, quiz_data: object) -> None:
    """Write quiz.json with the given data."""
    (course_dir / "quiz.json").write_text(
        json.dumps(quiz_data),
        encoding="utf-8",
    )


def _valid_quiz_payload(*, slug: str = "course") -> dict:
    """Return a minimal valid quiz payload."""
    return {
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
        _write_quiz(course_dir, _valid_quiz_payload(slug=slug))

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


class RuntimeLoaderFailClosedTests(unittest.TestCase):
    """Fail-closed handling for damaged runtime content."""

    def test_damaged_course_json_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            broken_dir = courses_dir / "broken"
            broken_dir.mkdir()
            (broken_dir / "course.json").write_text("{ invalid json", encoding="utf-8")

            courses = scan_courses(courses_dir)
            course = get_course(courses_dir, "broken")

        self.assertEqual(courses, [])
        self.assertIsNone(course)

    def test_course_json_array_root_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            broken_dir = courses_dir / "broken"
            broken_dir.mkdir()
            (broken_dir / "course.json").write_text("[1, 2, 3]", encoding="utf-8")

            courses = scan_courses(courses_dir)
            course = get_course(courses_dir, "broken")

        self.assertEqual(courses, [])
        self.assertIsNone(course)

    def test_damaged_course_does_not_block_valid_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "good")

            broken_dir = courses_dir / "broken"
            broken_dir.mkdir()
            (broken_dir / "course.json").write_text("{ broken", encoding="utf-8")

            courses = scan_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "good")

    def test_damaged_lesson_json_does_not_create_fake_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "course")

            (course_dir / "lesson_01" / "lesson.json").write_text(
                "{ broken",
                encoding="utf-8",
            )

            course = get_course(courses_dir, "course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.lessons, [])

    def test_valid_lessons_load_alongside_damaged_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "course")

            broken_lesson = course_dir / "lesson_broken"
            broken_lesson.mkdir()
            (broken_lesson / "lesson.json").write_text("{ broken", encoding="utf-8")

            valid_lesson = course_dir / "lesson_02"
            valid_lesson.mkdir()
            (valid_lesson / "lesson.json").write_text(
                json.dumps({"title": "Valid lesson", "order": 2}),
                encoding="utf-8",
            )

            course = get_course(courses_dir, "course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(len(course.lessons), 2)
        self.assertEqual(
            [lesson.path.name for lesson in course.lessons],
            ["lesson_01", "lesson_02"],
        )

    def test_damaged_quiz_json_yields_none_quiz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "course")
            (course_dir / "quiz.json").write_text("{ broken", encoding="utf-8")

            course = get_course(courses_dir, "course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.quiz)

    def test_quiz_with_damaged_question_is_rejected_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "course")

            quiz = _valid_quiz_payload(slug="course")
            quiz["questions"].append(
                {
                    "id": "q2",
                    "type": "single_choice",
                    "text": "",
                    "options": [
                        {"id": "a", "text": "Answer A"},
                        {"id": "b", "text": "Answer B"},
                    ],
                    "correct_option_ids": ["a"],
                }
            )
            _write_quiz(course_dir, quiz)

            course = get_course(courses_dir, "course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.quiz)

    def test_quiz_with_duplicate_option_id_is_rejected_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "course")

            quiz = _valid_quiz_payload(slug="course")
            quiz["questions"][0]["options"] = [
                {"id": "a", "text": "Answer A"},
                {"id": "a", "text": "Answer B"},
            ]
            _write_quiz(course_dir, quiz)

            course = get_course(courses_dir, "course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.quiz)

    def test_quiz_with_unknown_correct_option_is_rejected_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "course")

            quiz = _valid_quiz_payload(slug="course")
            quiz["questions"][0]["correct_option_ids"] = ["missing"]
            _write_quiz(course_dir, quiz)

            course = get_course(courses_dir, "course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.quiz)

    def test_quiz_with_empty_questions_is_not_exposed_in_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            course_dir = _write_minimal_course(courses_dir, "empty-quiz", with_quiz=False)
            _write_quiz(
                course_dir,
                {
                    "id": "empty-quiz_quiz",
                    "title": "Draft quiz",
                    "passing_score": 80,
                    "version": 1,
                    "randomize_questions": True,
                    "randomize_options": True,
                    "questions": [],
                },
            )

            course = get_course(courses_dir, "empty-quiz")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertIsNone(course.quiz)

    def test_valid_quiz_still_loads_unchanged(self) -> None:
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
        self.assertEqual(len(quiz.questions), 1)
        self.assertEqual(quiz.questions[0].id, "q1")
        self.assertEqual(len(quiz.questions[0].options), 2)

    def test_archived_course_is_not_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "archived_course", status="archived")

            courses = scan_courses(courses_dir)
            course = get_course(courses_dir, "archived_course")

        self.assertEqual(courses, [])
        self.assertIsNone(course)

    def test_oserror_on_base_dir_iterdir_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "good")

            with patch.object(
                Path,
                "iterdir",
                side_effect=OSError("permission denied"),
            ):
                courses = load_published_courses(courses_dir)

        self.assertEqual(courses, [])

    def test_oserror_on_single_course_does_not_block_other(self) -> None:
        original_load = runtime_loader._load_course_from_directory

        def load_with_oserror(course_dir: Path):
            if course_dir.name == "broken":
                raise OSError("read error")
            return original_load(course_dir)

        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "good")
            _write_minimal_course(courses_dir, "broken")

            with patch.object(
                runtime_loader,
                "_load_course_from_directory",
                side_effect=load_with_oserror,
            ):
                courses = scan_courses(courses_dir)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "good")


if __name__ == "__main__":
    unittest.main()
