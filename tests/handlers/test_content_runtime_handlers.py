"""Tests for ContentRuntime integration in Telegram handlers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from app.content.runtime import ContentRuntime
from app.content.runtime_loader import Course, Lesson, Quiz, QuizOption, QuizQuestion
from app.handlers.courses import show_course_card
from app.handlers.quiz import start_quiz
from app.handlers.start import show_courses


def _write_minimal_course(
    courses_dir: Path,
    slug: str,
    *,
    course_order: int = 1,
    status: str = "published",
) -> Path:
    """Create a minimal valid published course directory for handler tests."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "status": status,
                "order": course_order,
                "version": 1,
            }
        ),
        encoding="utf-8",
    )

    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": "First lesson", "order": 1}),
        encoding="utf-8",
    )

    return course_dir


def _sample_course(
    slug: str = "alpha",
    *,
    with_quiz: bool = False,
) -> Course:
    lesson = Lesson(
        path=Path(f"/tmp/{slug}/lesson_01"),
        number=1,
        title="Lesson 1",
        description="",
        image_path=None,
        narration_path=None,
    )
    quiz: Optional[Quiz] = None
    if with_quiz:
        quiz = Quiz(
            id=f"{slug}_quiz",
            title="Test",
            passing_score=80,
            questions=[
                QuizQuestion(
                    id="q1",
                    question_type="single_choice",
                    text="Question?",
                    options=[
                        QuizOption(id="a", text="A"),
                        QuizOption(id="b", text="B"),
                    ],
                    correct_option_ids=["a"],
                    explanation="",
                    lesson="lesson_01",
                    difficulty=1,
                    tags=[],
                    ai_context="",
                )
            ],
            version=1,
            randomize_questions=False,
            randomize_options=False,
        )

    return Course(
        slug=slug,
        title=f"Title {slug}",
        status="published",
        version=1,
        lessons=[lesson],
        cover_path=None,
        quiz=quiz,
    )


class StubContentRuntime:
    """Minimal stub that tracks calls without filesystem access."""

    def __init__(self, courses: list[Course]) -> None:
        self._courses = courses
        self._index = {course.slug: course for course in courses}
        self.get_courses_calls = 0
        self.get_course_calls = 0

    def get_courses(self) -> list[Course]:
        self.get_courses_calls += 1
        return list(self._courses)

    def get_course(self, slug: str) -> Optional[Course]:
        self.get_course_calls += 1
        return self._index.get(slug)


class ContentRuntimeHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Handler integration tests using injected ContentRuntime."""

    async def test_show_courses_uses_content_runtime(self) -> None:
        runtime = StubContentRuntime([_sample_course()])
        callback = AsyncMock()
        callback.from_user.id = 42
        callback.message = AsyncMock()
        callback.answer = AsyncMock()
        db_path = Path("/tmp/test.db")

        with patch(
            "app.handlers.start.progress_repository.get_course_progress",
            return_value=("not_started", 0),
        ):
            await show_courses(
                callback,
                content_runtime=runtime,
                db_path=db_path,
            )

        self.assertEqual(runtime.get_courses_calls, 1)
        callback.message.edit_text.assert_awaited_once()

    async def test_show_course_card_uses_get_course(self) -> None:
        runtime = StubContentRuntime([_sample_course("brands")])
        callback = AsyncMock()
        callback.data = "course_card:brands"
        callback.from_user.id = 42
        callback.message = AsyncMock()
        callback.answer = AsyncMock()
        db_path = Path("/tmp/test.db")

        with patch(
            "app.handlers.courses.progress_repository.get_course_progress",
            return_value=("not_started", 0),
        ):
            await show_course_card(
                callback,
                content_runtime=runtime,
                db_path=db_path,
            )

        self.assertEqual(runtime.get_course_calls, 1)
        callback.message.edit_text.assert_awaited_once()

    async def test_missing_slug_is_handled_safely(self) -> None:
        runtime = StubContentRuntime([_sample_course("brands")])
        callback = AsyncMock()
        callback.data = "course_card:missing"
        callback.from_user.id = 42
        callback.message = AsyncMock()
        callback.answer = AsyncMock()
        db_path = Path("/tmp/test.db")

        await show_course_card(
            callback,
            content_runtime=runtime,
            db_path=db_path,
        )

        callback.answer.assert_awaited_once_with(
            "Курс не найден.",
            show_alert=True,
        )
        callback.message.edit_text.assert_not_awaited()

    async def test_start_quiz_uses_content_runtime(self) -> None:
        runtime = StubContentRuntime([_sample_course("brands", with_quiz=True)])
        callback = AsyncMock()
        callback.data = "quiz_start:brands"
        callback.from_user.id = 42
        callback.message = AsyncMock()
        callback.answer = AsyncMock()
        db_path = Path("/tmp/test.db")

        with patch(
            "app.handlers.quiz.quiz_repository.create_attempt",
        ):
            await start_quiz(
                callback,
                content_runtime=runtime,
                db_path=db_path,
            )

        self.assertEqual(runtime.get_course_calls, 1)
        callback.message.answer.assert_awaited_once()

    async def test_two_actions_reuse_same_runtime_without_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=__import__(
                    "app.content.runtime_loader",
                    fromlist=["load_published_courses"],
                ).load_published_courses,
            ) as loader:
                callback_list = AsyncMock()
                callback_list.from_user.id = 1
                callback_list.message = AsyncMock()
                callback_list.answer = AsyncMock()

                callback_card = AsyncMock()
                callback_card.data = "course_card:alpha"
                callback_card.from_user.id = 1
                callback_card.message = AsyncMock()
                callback_card.answer = AsyncMock()

                db_path = Path("/tmp/test.db")

                with patch(
                    "app.handlers.start.progress_repository.get_course_progress",
                    return_value=("not_started", 0),
                ):
                    await show_courses(
                        callback_list,
                        content_runtime=runtime,
                        db_path=db_path,
                    )

                with patch(
                    "app.handlers.courses.progress_repository.get_course_progress",
                    return_value=("not_started", 0),
                ):
                    await show_course_card(
                        callback_card,
                        content_runtime=runtime,
                        db_path=db_path,
                    )

            loader.assert_called_once()

    async def test_handler_uses_injected_runtime_instance(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = [_sample_course()]

        callback = AsyncMock()
        callback.from_user.id = 1
        callback.message = AsyncMock()
        callback.answer = AsyncMock()

        with patch(
            "app.handlers.start.progress_repository.get_course_progress",
            return_value=("not_started", 0),
        ):
            await show_courses(
                callback,
                content_runtime=runtime,
                db_path=Path("/tmp/test.db"),
            )

        runtime.get_courses.assert_called_once()
