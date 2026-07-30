"""Tests for runtime lifecycle management (``app.content.runtime_manager``)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.content.runtime import ContentRuntime
from app.content.runtime_manager import (
    ContentRuntimeManager,
    RuntimeRefreshStats,
    RuntimeState,
)


def _write_minimal_course(courses_dir: Path, slug: str) -> None:
    """Create a minimal valid published course directory."""
    course_dir = courses_dir / slug
    course_dir.mkdir()

    (course_dir / "course.json").write_text(
        json.dumps(
            {
                "title": f"Title {slug}",
                "status": "published",
                "order": 1,
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


class ContentRuntimeManagerTests(unittest.TestCase):
    """Tests for :class:`ContentRuntimeManager`."""

    def test_refresh_calls_runtime_refresh(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.side_effect = [[], []]
        manager = ContentRuntimeManager(runtime)

        manager.refresh()

        runtime.refresh.assert_called_once_with()

    def test_refresh_returns_stats_with_correct_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            manager = ContentRuntimeManager(runtime)

            stats = manager.refresh()

        self.assertIsInstance(stats, RuntimeRefreshStats)
        self.assertEqual(stats.courses_before, 1)
        self.assertEqual(stats.courses_after, 1)

    def test_changed_false_when_course_count_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            manager = ContentRuntimeManager(runtime)

            stats = manager.refresh()

        self.assertFalse(stats.changed)
        self.assertEqual(stats.courses_before, stats.courses_after)

    def test_changed_true_when_course_count_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            manager = ContentRuntimeManager(runtime)
            runtime.get_courses()

            _write_minimal_course(courses_dir, "beta")
            stats = manager.refresh()

        self.assertTrue(stats.changed)
        self.assertEqual(stats.courses_before, 1)
        self.assertEqual(stats.courses_after, 2)

    def test_refreshed_at_is_set(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = []
        manager = ContentRuntimeManager(runtime)

        with patch(
            "app.content.runtime_manager._utc_timestamp",
            return_value="2026-07-30T18:00:00Z",
        ):
            stats = manager.refresh()

        self.assertEqual(stats.refreshed_at, "2026-07-30T18:00:00Z")

    def test_manager_does_not_modify_runtime_without_refresh(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        manager = ContentRuntimeManager(runtime)

        self.assertIs(manager.runtime, runtime)
        runtime.refresh.assert_not_called()
        runtime.get_courses.assert_not_called()

    def test_get_state_returns_runtime_state(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = [MagicMock(), MagicMock()]
        manager = ContentRuntimeManager(runtime)

        state = manager.get_state()

        self.assertIsInstance(state, RuntimeState)
        self.assertEqual(state.courses_count, 2)

    def test_get_state_last_refreshed_at_none_before_first_refresh(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = []
        manager = ContentRuntimeManager(runtime)

        state = manager.get_state()

        self.assertIsNone(state.last_refreshed_at)

    def test_get_state_courses_count_matches_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            _write_minimal_course(courses_dir, "beta")
            runtime = ContentRuntime(courses_dir)
            manager = ContentRuntimeManager(runtime)

            state = manager.get_state()

        self.assertEqual(state.courses_count, 2)

    def test_get_state_after_refresh_shares_timestamp_with_stats(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = []
        manager = ContentRuntimeManager(runtime)

        with patch(
            "app.content.runtime_manager._utc_timestamp",
            return_value="2026-07-30T18:00:00Z",
        ):
            stats = manager.refresh()
            state = manager.get_state()

        self.assertEqual(state.last_refreshed_at, stats.refreshed_at)
        self.assertEqual(state.last_refreshed_at, "2026-07-30T18:00:00Z")

    def test_utc_timestamp_called_once_per_refresh(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = []
        manager = ContentRuntimeManager(runtime)

        with patch(
            "app.content.runtime_manager._utc_timestamp",
            return_value="2026-07-30T18:00:00Z",
        ) as timestamp_mock:
            manager.refresh()

        timestamp_mock.assert_called_once_with()

    def test_get_state_does_not_call_runtime_refresh(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = []
        manager = ContentRuntimeManager(runtime)

        manager.get_state()

        runtime.refresh.assert_not_called()

    def test_multiple_get_state_calls_do_not_change_last_refreshed_at(self) -> None:
        runtime = MagicMock(spec=ContentRuntime)
        runtime.get_courses.return_value = []
        manager = ContentRuntimeManager(runtime)

        with patch(
            "app.content.runtime_manager._utc_timestamp",
            return_value="2026-07-30T18:00:00Z",
        ):
            manager.refresh()
            first_state = manager.get_state()
            second_state = manager.get_state()

        self.assertEqual(first_state.last_refreshed_at, "2026-07-30T18:00:00Z")
        self.assertEqual(second_state.last_refreshed_at, "2026-07-30T18:00:00Z")
        runtime.refresh.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
