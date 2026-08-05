"""Tests for AI provider interfaces (``app.ai.interfaces``)."""

from __future__ import annotations

import unittest

from app.ai.interfaces import (
    CourseGenerationAI,
    LessonGenerationRequest,
    LessonGenerationResult,
)
from app.content.lesson_builder import LessonCandidate
from app.content.practical_task import PracticalTask


class LessonGenerationRequestTests(unittest.TestCase):
    """Tests for :class:`LessonGenerationRequest`."""

    def test_create_request(self) -> None:
        lessons = [
            LessonCandidate(title="Section 1", content="First lesson."),
            LessonCandidate(title="Section 2", content="Second lesson."),
        ]

        request = LessonGenerationRequest(lessons=lessons)

        self.assertEqual(request.lessons, lessons)
        self.assertIsInstance(request.lessons, list)
        self.assertTrue(all(isinstance(lesson, LessonCandidate) for lesson in request.lessons))


class LessonGenerationResultTests(unittest.TestCase):
    """Tests for :class:`LessonGenerationResult`."""

    def test_create_result(self) -> None:
        lessons = [
            LessonCandidate(title="Refined 1", content="Refined content."),
        ]

        result = LessonGenerationResult(lessons=lessons)

        self.assertEqual(result.lessons, lessons)
        self.assertIsInstance(result.lessons, list)
        self.assertTrue(all(isinstance(lesson, LessonCandidate) for lesson in result.lessons))


class StructuredPracticalTaskContractTests(unittest.TestCase):
    """Tests for optional structured practical tasks in the AI contract."""

    def test_request_accepts_lesson_with_structured_practical_task(self) -> None:
        task = PracticalTask(
            title="Inspect the area",
            description="Walk through the work zone.",
            expected_result="Hazards are documented.",
            estimated_minutes=15,
        )
        lesson = LessonCandidate(
            title="Safety basics",
            content="Lesson body.",
            structured_practical_task=task,
        )

        request = LessonGenerationRequest(lessons=[lesson])

        self.assertIs(request.lessons[0].structured_practical_task, task)
        self.assertEqual(request.lessons[0].practical_task, "")

    def test_result_accepts_lesson_with_structured_practical_task(self) -> None:
        task = PracticalTask(
            title="Apply the checklist",
            description="Complete every item before starting work.",
            expected_result="All checklist items are checked.",
        )
        lesson = LessonCandidate(
            title="Safety basics",
            content="Lesson body.",
            structured_practical_task=task,
        )

        result = LessonGenerationResult(lessons=[lesson])

        self.assertIs(result.lessons[0].structured_practical_task, task)

    def test_legacy_practical_task_string_remains_compatible(self) -> None:
        lesson = LessonCandidate(
            title="Safety basics",
            content="Lesson body.",
            practical_task="Complete the safety checklist.",
        )

        result = LessonGenerationResult(lessons=[lesson])

        self.assertEqual(result.lessons[0].practical_task, "Complete the safety checklist.")
        self.assertIsNone(result.lessons[0].structured_practical_task)

    def test_lesson_without_practical_fields_uses_defaults(self) -> None:
        lesson = LessonCandidate(title="Safety basics", content="Lesson body.")

        request = LessonGenerationRequest(lessons=[lesson])

        self.assertEqual(request.lessons[0].practical_task, "")
        self.assertIsNone(request.lessons[0].structured_practical_task)


class CourseGenerationAIProtocolTests(unittest.TestCase):
    """Tests for :class:`CourseGenerationAI` structural typing."""

    def test_protocol_accepts_conforming_implementation(self) -> None:
        class StubAI:
            def generate_lessons(
                self,
                request: LessonGenerationRequest,
            ) -> LessonGenerationResult:
                return LessonGenerationResult(lessons=request.lessons)

        ai: CourseGenerationAI = StubAI()
        request = LessonGenerationRequest(
            lessons=[
                LessonCandidate(title="Section 1", content="Content."),
            ]
        )

        result = ai.generate_lessons(request)

        self.assertEqual(result.lessons, request.lessons)
        self.assertIsInstance(result, LessonGenerationResult)
