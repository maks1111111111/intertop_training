"""Tests for lesson delivery in courses handler."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.content.runtime_loader import Course, Lesson
from app.handlers.courses import _send_lesson


def _sample_course(*, lesson: Lesson) -> Course:
    return Course(
        slug="alpha",
        title="Alpha Course",
        status="published",
        version=1,
        lessons=[lesson],
        cover_path=None,
        quiz=None,
    )


def _sample_lesson(**overrides: object) -> Lesson:
    defaults = {
        "path": Path("lesson_01"),
        "number": 1,
        "title": "Sample Lesson",
        "description": "Main lesson text.",
        "image_path": None,
        "narration_path": None,
        "practical_task": "",
        "checklist": (),
        "common_mistakes": (),
        "key_takeaways": (),
        "application_tips": (),
    }
    defaults.update(overrides)
    return Lesson(**defaults)


class SendLessonTests(unittest.IsolatedAsyncioTestCase):
    async def test_lesson_without_image_sends_body_as_single_message(self) -> None:
        lesson = _sample_lesson(
            description="Plain lesson body.",
            practical_task="Practice task.",
        )
        course = _sample_course(lesson=lesson)

        callback = MagicMock()
        callback.message = AsyncMock()

        await _send_lesson(
            callback=callback,
            course=course,
            lesson=lesson,
            lesson_index=0,
        )

        callback.message.answer.assert_any_call(
            "Plain lesson body.\n\n🛠 Практическое задание\nPractice task.",
        )
        callback.message.answer_photo.assert_not_called()

    @patch("app.handlers.courses.FSInputFile")
    async def test_lesson_with_image_sends_body_separately_from_photo(
        self,
        mock_fs_input_file: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "image.jpg"
            image_path.write_bytes(b"fake-image")

            body_text = (
                "Main lesson text.\n\n"
                "🛠 Практическое задание\nPractice task."
            )
            lesson = _sample_lesson(
                description="Main lesson text.",
                practical_task="Practice task.",
                image_path=image_path,
            )
            course = _sample_course(lesson=lesson)

            callback = MagicMock()
            callback.message = AsyncMock()

            await _send_lesson(
                callback=callback,
                course=course,
                lesson=lesson,
                lesson_index=0,
            )

            callback.message.answer_photo.assert_called_once()
            photo_kwargs = callback.message.answer_photo.call_args.kwargs
            self.assertNotIn("caption", photo_kwargs)
            mock_fs_input_file.assert_called_once_with(image_path)

            callback.message.answer.assert_any_call(body_text)

    @patch("app.handlers.courses.FSInputFile")
    async def test_lesson_with_image_and_empty_body_sends_photo_only(
        self,
        mock_fs_input_file: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "image.jpg"
            image_path.write_bytes(b"fake-image")

            lesson = _sample_lesson(
                description="",
                image_path=image_path,
            )
            course = _sample_course(lesson=lesson)

            callback = MagicMock()
            callback.message = AsyncMock()

            await _send_lesson(
                callback=callback,
                course=course,
                lesson=lesson,
                lesson_index=0,
            )

            callback.message.answer_photo.assert_called_once()
            photo_kwargs = callback.message.answer_photo.call_args.kwargs
            self.assertNotIn("caption", photo_kwargs)

            body_calls = [
                call
                for call in callback.message.answer.call_args_list
                if call.args
                and call.args[0]
                not in ("Выберите действие:",)
                and not call.kwargs.get("parse_mode")
            ]
            self.assertEqual(body_calls, [])


if __name__ == "__main__":
    unittest.main()
