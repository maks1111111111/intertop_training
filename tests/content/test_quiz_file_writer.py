"""Tests for quiz file writing (``app.content.quiz_file_writer``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.content.quiz_file_writer import QuizFileWriter
from app.content.quiz_writer import (
    QuizDraft,
    QuizOptionDraft,
    QuizQuestionDraft,
)


def _sample_draft(
    *,
    questions: tuple[QuizQuestionDraft, ...] | None = None,
) -> QuizDraft:
    if questions is None:
        questions = (
            QuizQuestionDraft(
                id="q1",
                question_type="single_choice",
                text="What should an employee do?",
                options=(
                    QuizOptionDraft(id="a", text="Correct answer"),
                    QuizOptionDraft(id="b", text="Incorrect answer 1"),
                    QuizOptionDraft(id="c", text="Incorrect answer 2"),
                    QuizOptionDraft(id="d", text="Incorrect answer 3"),
                ),
                correct_option_ids=("a",),
                explanation="",
                lesson="lesson_01",
                difficulty=1,
                tags=(),
                ai_context="",
            ),
        )

    return QuizDraft(
        id="brands_quiz",
        title="Final course quiz",
        passing_score=80,
        version=1,
        randomize_questions=True,
        randomize_options=True,
        questions=questions,
    )


class QuizFileWriterTests(unittest.TestCase):
    """Tests for :class:`QuizFileWriter`."""

    def setUp(self) -> None:
        self.writer = QuizFileWriter()

    def test_creates_quiz_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()

            quiz_path = self.writer.write(draft, course_dir)

            self.assertTrue(quiz_path.is_file())
            self.assertEqual(quiz_path, course_dir / "quiz.json")

    def test_returns_path_to_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()

            quiz_path = self.writer.write(draft, course_dir)

            self.assertEqual(quiz_path, course_dir / "quiz.json")

    def test_writes_top_level_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()

            self.writer.write(draft, course_dir)
            manifest = json.loads(
                (course_dir / "quiz.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["id"], "brands_quiz")
            self.assertEqual(manifest["title"], "Final course quiz")
            self.assertEqual(manifest["passing_score"], 80)
            self.assertEqual(manifest["version"], 1)
            self.assertTrue(manifest["randomize_questions"])
            self.assertTrue(manifest["randomize_options"])
            self.assertIsInstance(manifest["questions"], list)

    def test_writes_question_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()

            self.writer.write(draft, course_dir)
            manifest = json.loads(
                (course_dir / "quiz.json").read_text(encoding="utf-8")
            )
            question = manifest["questions"][0]

            self.assertEqual(question["id"], "q1")
            self.assertEqual(question["type"], "single_choice")
            self.assertEqual(question["text"], "What should an employee do?")
            self.assertEqual(
                question["options"],
                [
                    {"id": "a", "text": "Correct answer"},
                    {"id": "b", "text": "Incorrect answer 1"},
                    {"id": "c", "text": "Incorrect answer 2"},
                    {"id": "d", "text": "Incorrect answer 3"},
                ],
            )
            self.assertEqual(question["correct_option_ids"], ["a"])
            self.assertEqual(question["explanation"], "")
            self.assertEqual(question["lesson"], "lesson_01")
            self.assertEqual(question["difficulty"], 1)
            self.assertEqual(question["tags"], [])
            self.assertEqual(question["ai_context"], "")

    def test_question_type_field_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()

            self.writer.write(draft, course_dir)
            manifest = json.loads(
                (course_dir / "quiz.json").read_text(encoding="utf-8")
            )

            self.assertNotIn("question_type", manifest["questions"][0])

    def test_preserves_question_order(self) -> None:
        questions = (
            QuizQuestionDraft(
                id="q1",
                question_type="single_choice",
                text="First question",
                options=(
                    QuizOptionDraft(id="a1", text="A1"),
                    QuizOptionDraft(id="b1", text="B1"),
                    QuizOptionDraft(id="c1", text="C1"),
                    QuizOptionDraft(id="d1", text="D1"),
                ),
                correct_option_ids=("a1",),
                explanation="",
                lesson="lesson_01",
                difficulty=1,
                tags=(),
                ai_context="",
            ),
            QuizQuestionDraft(
                id="q2",
                question_type="single_choice",
                text="Second question",
                options=(
                    QuizOptionDraft(id="a2", text="A2"),
                    QuizOptionDraft(id="b2", text="B2"),
                    QuizOptionDraft(id="c2", text="C2"),
                    QuizOptionDraft(id="d2", text="D2"),
                ),
                correct_option_ids=("b2",),
                explanation="",
                lesson="lesson_02",
                difficulty=1,
                tags=(),
                ai_context="",
            ),
        )
        draft = _sample_draft(questions=questions)

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            self.writer.write(draft, course_dir)
            manifest = json.loads(
                (course_dir / "quiz.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                [question["id"] for question in manifest["questions"]],
                ["q1", "q2"],
            )

    def test_preserves_option_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()

            self.writer.write(draft, course_dir)
            manifest = json.loads(
                (course_dir / "quiz.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                [option["id"] for option in manifest["questions"][0]["options"]],
                ["a", "b", "c", "d"],
            )

    def test_preserves_unicode_without_ascii_escaping(self) -> None:
        questions = (
            QuizQuestionDraft(
                id="q1",
                question_type="single_choice",
                text="Что должен сделать сотрудник?",
                options=(
                    QuizOptionDraft(id="a", text="Правильный ответ"),
                    QuizOptionDraft(id="b", text="Қате жауап 1"),
                    QuizOptionDraft(id="c", text="Қате жауап 2"),
                    QuizOptionDraft(id="d", text="Қате жауап 3"),
                ),
                correct_option_ids=("a",),
                explanation="",
                lesson="lesson_01",
                difficulty=1,
                tags=(),
                ai_context="",
            ),
        )
        draft = QuizDraft(
            id="brands_quiz",
            title="Итоговый тест",
            passing_score=80,
            version=1,
            randomize_questions=True,
            randomize_options=True,
            questions=questions,
        )

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            quiz_path = self.writer.write(draft, course_dir)
            raw_text = quiz_path.read_text(encoding="utf-8")

            self.assertIn("Что должен сделать сотрудник?", raw_text)
            self.assertIn("Правильный ответ", raw_text)
            self.assertIn("Қате жауап 1", raw_text)
            self.assertNotIn("\\u", raw_text)

    def test_writes_empty_questions_list(self) -> None:
        draft = _sample_draft(questions=())

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            self.writer.write(draft, course_dir)
            manifest = json.loads(
                (course_dir / "quiz.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["questions"], [])

    def test_missing_directory_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = Path(tmp) / "missing"
            draft = _sample_draft()

            with self.assertRaises(FileNotFoundError):
                self.writer.write(draft, missing_dir)

    def test_file_instead_of_directory_raises_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_file = Path(tmp) / "not-a-dir"
            course_file.write_text("stub", encoding="utf-8")
            draft = _sample_draft()

            with self.assertRaises(NotADirectoryError):
                self.writer.write(draft, course_file)

    def test_draft_is_not_mutated(self) -> None:
        draft = _sample_draft()
        expected = QuizDraft(
            id=draft.id,
            title=draft.title,
            passing_score=draft.passing_score,
            version=draft.version,
            randomize_questions=draft.randomize_questions,
            randomize_options=draft.randomize_options,
            questions=draft.questions,
        )

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            self.writer.write(draft, course_dir)

            self.assertEqual(draft, expected)

    def test_output_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "brands"
            course_dir.mkdir()
            draft = _sample_draft()
            quiz_path = self.writer.write(draft, course_dir)

            manifest = json.loads(quiz_path.read_text(encoding="utf-8"))

            self.assertIsInstance(manifest, dict)
            self.assertIn("questions", manifest)
