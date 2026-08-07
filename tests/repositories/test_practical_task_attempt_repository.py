"""Tests for practical_task_attempt_repository."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.ai.review_interfaces import ReviewFeedback, ReviewResult
from app.database.db import get_connection, initialize_database, upsert_telegram_user
from app.repositories import practical_task_attempt_repository as repository


def _sample_review_result(
    *,
    score: int = 8,
    max_score: int = 10,
    passed: bool = True,
    summary: str = "Good practical answer.",
    strengths: tuple[str, ...] = ("Identified hazards",),
    improvements: tuple[str, ...] = ("Add more detail",),
) -> ReviewResult:
    return ReviewResult(
        score=score,
        max_score=max_score,
        passed=passed,
        feedback=ReviewFeedback(
            summary=summary,
            strengths=strengths,
            improvements=improvements,
        ),
    )


class PracticalTaskAttemptRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        initialize_database(self.db_path)
        upsert_telegram_user(
            self.db_path,
            telegram_id=1001,
            username="learner",
            first_name="Test",
            last_name="User",
        )
        upsert_telegram_user(
            self.db_path,
            telegram_id=2002,
            username="other",
            first_name="Other",
            last_name="User",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _create_sample_attempt(
        self,
        *,
        telegram_id: int = 1001,
        course_slug: str = "safety",
        lesson_slug: str = "lesson_01",
        task_title: str = "Inspect the work area",
        task_description: str = "Walk through the area and identify hazards.",
        expected_result: str = "All hazards are documented and addressed.",
        learner_answer: str = "I checked the floor and removed loose cables.",
    ) -> int:
        attempt_id = repository.create_attempt(
            self.db_path,
            telegram_id=telegram_id,
            course_slug=course_slug,
            lesson_slug=lesson_slug,
            task_title=task_title,
            task_description=task_description,
            expected_result=expected_result,
            learner_answer=learner_answer,
        )
        self.assertIsNotNone(attempt_id)
        return attempt_id  # type: ignore[return-value]

    def test_create_attempt_creates_pending_attempt(self) -> None:
        attempt_id = self._create_sample_attempt()
        attempt = repository.get_attempt(self.db_path, attempt_id)

        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.status, "pending")
        self.assertIsNone(attempt.score)
        self.assertIsNone(attempt.max_score)
        self.assertIsNone(attempt.passed)
        self.assertIsNone(attempt.feedback_summary)
        self.assertEqual(attempt.strengths, ())
        self.assertEqual(attempt.improvements, ())
        self.assertIsNone(attempt.reviewed_at)

    def test_create_attempt_preserves_task_snapshot_and_answer(self) -> None:
        attempt_id = self._create_sample_attempt(
            task_title="  Заголовок задания  ",
            task_description="Описание на русском.",
            expected_result="Ожидаемый результат.",
            learner_answer="Ответ сотрудника на казахском: қауіпсіздік.",
        )
        attempt = repository.get_attempt(self.db_path, attempt_id)

        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.task_title, "  Заголовок задания  ")
        self.assertEqual(attempt.task_description, "Описание на русском.")
        self.assertEqual(attempt.expected_result, "Ожидаемый результат.")
        self.assertEqual(attempt.learner_answer, "Ответ сотрудника на казахском: қауіпсіздік.")

    def test_create_attempt_unknown_telegram_id_returns_none(self) -> None:
        attempt_id = repository.create_attempt(
            self.db_path,
            telegram_id=9999,
            course_slug="safety",
            lesson_slug="lesson_01",
            task_title="Title",
            task_description="Description",
            expected_result="Expected",
            learner_answer="Answer",
        )

        self.assertIsNone(attempt_id)

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM practical_task_attempts"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_get_attempt_unknown_id_returns_none(self) -> None:
        self.assertIsNone(repository.get_attempt(self.db_path, 99999))

    def test_complete_review_persists_score_and_passed(self) -> None:
        attempt_id = self._create_sample_attempt()
        updated = repository.complete_review(
            self.db_path,
            attempt_id,
            _sample_review_result(score=7, max_score=10, passed=True),
        )

        self.assertTrue(updated)
        attempt = repository.get_attempt(self.db_path, attempt_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.score, 7)
        self.assertEqual(attempt.max_score, 10)
        self.assertTrue(attempt.passed)

    def test_complete_review_persists_feedback_summary(self) -> None:
        attempt_id = self._create_sample_attempt()
        repository.complete_review(
            self.db_path,
            attempt_id,
            _sample_review_result(summary="Краткий итог проверки."),
        )

        attempt = repository.get_attempt(self.db_path, attempt_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.feedback_summary, "Краткий итог проверки.")

    def test_complete_review_serializes_strengths_and_improvements(self) -> None:
        attempt_id = self._create_sample_attempt()
        repository.complete_review(
            self.db_path,
            attempt_id,
            _sample_review_result(
                strengths=("Сильная сторона", "Ещё одна"),
                improvements=("Улучшение",),
            ),
        )

        attempt = repository.get_attempt(self.db_path, attempt_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.strengths, ("Сильная сторона", "Ещё одна"))
        self.assertEqual(attempt.improvements, ("Улучшение",))

    def test_complete_review_preserves_unicode_in_json(self) -> None:
        attempt_id = self._create_sample_attempt()
        repository.complete_review(
            self.db_path,
            attempt_id,
            _sample_review_result(
                strengths=("Қазақша пункт",),
                improvements=("Русский пункт",),
            ),
        )

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT feedback_strengths_json, feedback_improvements_json
                FROM practical_task_attempts
                WHERE id = ?
                """,
                (attempt_id,),
            ).fetchone()

        self.assertIn("Қазақша", row["feedback_strengths_json"])
        self.assertIn("Русский", row["feedback_improvements_json"])

    def test_complete_review_sets_status_reviewed_and_reviewed_at(self) -> None:
        attempt_id = self._create_sample_attempt()
        repository.complete_review(
            self.db_path,
            attempt_id,
            _sample_review_result(),
        )

        attempt = repository.get_attempt(self.db_path, attempt_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.status, "reviewed")
        self.assertIsNotNone(attempt.reviewed_at)

    def test_complete_review_does_not_update_already_reviewed_attempt(self) -> None:
        attempt_id = self._create_sample_attempt()
        first_result = _sample_review_result(
            score=5,
            max_score=10,
            passed=False,
            summary="First review",
            strengths=("First strength",),
            improvements=("First improvement",),
        )
        second_result = _sample_review_result(
            score=9,
            max_score=10,
            passed=True,
            summary="Second review",
            strengths=("Second strength",),
            improvements=("Second improvement",),
        )

        self.assertTrue(repository.complete_review(self.db_path, attempt_id, first_result))
        self.assertFalse(repository.complete_review(self.db_path, attempt_id, second_result))

        attempt = repository.get_attempt(self.db_path, attempt_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.score, 5)
        self.assertFalse(attempt.passed)
        self.assertEqual(attempt.feedback_summary, "First review")
        self.assertEqual(attempt.strengths, ("First strength",))
        self.assertEqual(attempt.improvements, ("First improvement",))
        self.assertEqual(attempt.status, "reviewed")

    def test_get_attempts_for_lesson_filters_by_user_course_and_lesson(self) -> None:
        own_attempt = self._create_sample_attempt(
            course_slug="safety",
            lesson_slug="lesson_01",
        )
        self._create_sample_attempt(
            telegram_id=2002,
            course_slug="safety",
            lesson_slug="lesson_01",
        )
        self._create_sample_attempt(
            course_slug="other-course",
            lesson_slug="lesson_01",
        )
        self._create_sample_attempt(
            course_slug="safety",
            lesson_slug="lesson_02",
        )

        attempts = repository.get_attempts_for_lesson(
            self.db_path,
            telegram_id=1001,
            course_slug="safety",
            lesson_slug="lesson_01",
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].id, own_attempt)

    def test_get_attempts_for_lesson_orders_newest_first(self) -> None:
        first_id = self._create_sample_attempt(learner_answer="First answer")
        second_id = self._create_sample_attempt(learner_answer="Second answer")

        attempts = repository.get_attempts_for_lesson(
            self.db_path,
            telegram_id=1001,
            course_slug="safety",
            lesson_slug="lesson_01",
        )

        self.assertEqual([attempt.id for attempt in attempts], [second_id, first_id])

    def test_get_attempts_for_lesson_respects_limit(self) -> None:
        for index in range(3):
            self._create_sample_attempt(learner_answer=f"Answer {index}")

        attempts = repository.get_attempts_for_lesson(
            self.db_path,
            telegram_id=1001,
            course_slug="safety",
            lesson_slug="lesson_01",
            limit=2,
        )

        self.assertEqual(len(attempts), 2)

    def test_get_attempts_for_lesson_non_positive_limit_returns_empty(self) -> None:
        self._create_sample_attempt()

        self.assertEqual(
            repository.get_attempts_for_lesson(
                self.db_path,
                telegram_id=1001,
                course_slug="safety",
                lesson_slug="lesson_01",
                limit=0,
            ),
            [],
        )
        self.assertEqual(
            repository.get_attempts_for_lesson(
                self.db_path,
                telegram_id=1001,
                course_slug="safety",
                lesson_slug="lesson_01",
                limit=-1,
            ),
            [],
        )

    def test_pending_attempt_reads_with_empty_review_fields(self) -> None:
        attempt_id = self._create_sample_attempt()
        attempt = repository.get_attempt(self.db_path, attempt_id)

        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertEqual(attempt.telegram_id, 1001)
        self.assertEqual(attempt.course_slug, "safety")
        self.assertEqual(attempt.lesson_slug, "lesson_01")
        self.assertIsNotNone(attempt.started_at)


if __name__ == "__main__":
    unittest.main()
