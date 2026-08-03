"""Tests for cached runtime access (``app.content.runtime``)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.content.runtime import (
    ContentRuntime,
    _SCAN_ERROR_FINGERPRINT,
    _content_fingerprint,
)
from app.content.runtime_loader import load_published_courses


def _write_minimal_course(
    courses_dir: Path,
    slug: str,
    *,
    course_order: int = 1,
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


def _write_quiz_json(course_dir: Path) -> None:
    """Create a minimal runtime-compatible quiz.json in *course_dir*."""
    (course_dir / "quiz.json").write_text(
        json.dumps(
            {
                "id": f"{course_dir.name}_quiz",
                "title": "Quiz",
                "passing_score": 80,
                "questions": [
                    {
                        "id": "q1",
                        "type": "single_choice",
                        "text": "Question?",
                        "options": [
                            {"id": "a", "text": "Yes"},
                            {"id": "b", "text": "No"},
                        ],
                        "correct_option_ids": ["a"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_lesson(
    course_dir: Path,
    lesson_slug: str,
    *,
    title: str,
    order: int,
) -> None:
    """Create an additional lesson directory under *course_dir*."""
    lesson_dir = course_dir / lesson_slug
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text(
        json.dumps({"title": title, "order": order}),
        encoding="utf-8",
    )


class ContentRuntimeTests(unittest.TestCase):
    """Tests for :class:`ContentRuntime`."""

    def test_first_load_reads_filesystem_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                first = runtime.get_courses()
                second = runtime.get_courses()

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].slug, "alpha")
        self.assertEqual(second, first)
        loader.assert_called_once()

    def test_repeated_calls_use_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_course("alpha")
                runtime.get_course("alpha")
                runtime.get_courses()

        loader.assert_called_once()

    def test_refresh_reloads_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                runtime.refresh()

        self.assertEqual(loader.call_count, 2)

    def test_after_refresh_get_courses_does_not_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                runtime.refresh()
                runtime.get_courses()

        self.assertEqual(loader.call_count, 2)

    def test_get_course_uses_slug_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course = runtime.get_course("alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "alpha")
        loader.assert_called_once()

    def test_missing_slug_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            course = runtime.get_course("missing")

        self.assertIsNone(course)

    def test_empty_directory_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                first = runtime.get_courses()
                second = runtime.get_courses()

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        loader.assert_called_once()

    def test_refresh_picks_up_new_courses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            self.assertEqual(runtime.get_courses(), [])

            _write_minimal_course(courses_dir, "new_course")
            runtime.refresh()

            courses = runtime.get_courses()

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "new_course")

    def test_after_refresh_new_course_available_via_get_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            self.assertIsNone(runtime.get_course("new_course"))

            _write_minimal_course(courses_dir, "new_course")
            runtime.refresh()

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course = runtime.get_course("new_course")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "new_course")
        loader.assert_not_called()

    def test_independent_instances_for_same_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            first = ContentRuntime(courses_dir)
            second = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                first.get_courses()
                second.get_courses()

        self.assertEqual(loader.call_count, 2)
        self.assertIsNot(first, second)

    def test_refresh_updates_list_and_index_consistently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            _write_minimal_course(courses_dir, "beta", course_order=2)
            runtime.refresh()

            courses = runtime.get_courses()
            slugs = {course.slug for course in courses}

            self.assertEqual(slugs, {"alpha", "beta"})
            self.assertIsNotNone(runtime.get_course("alpha"))
            self.assertIsNotNone(runtime.get_course("beta"))
            self.assertIsNone(runtime.get_course("missing"))


class ContentRuntimeAutoRefreshTests(unittest.TestCase):
    """Tests for automatic cache refresh when course files change on disk."""

    def test_new_course_auto_appears_via_get_courses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                _write_minimal_course(courses_dir, "beta", course_order=2)
                courses = runtime.get_courses()

        self.assertEqual(loader.call_count, 2)
        self.assertEqual({course.slug for course in courses}, {"alpha", "beta"})

    def test_new_course_auto_available_via_get_course(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                _write_minimal_course(courses_dir, "beta", course_order=2)
                course = runtime.get_course("beta")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.slug, "beta")
        self.assertEqual(loader.call_count, 2)

    def test_deleted_course_disappears_without_manual_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            alpha_dir = _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                shutil.rmtree(alpha_dir)
                courses = runtime.get_courses()
                missing = runtime.get_course("alpha")

        self.assertEqual(loader.call_count, 2)
        self.assertEqual(courses, [])
        self.assertIsNone(missing)

    def test_course_json_change_updates_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            alpha_dir = _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            course_json = alpha_dir / "course.json"
            data = json.loads(course_json.read_text(encoding="utf-8"))
            data["title"] = "Updated Title"
            course_json.write_text(json.dumps(data), encoding="utf-8")

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course = runtime.get_course("alpha")

        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.title, "Updated Title")
        loader.assert_called_once()

    def test_adding_quiz_json_makes_course_quiz_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            alpha_dir = _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            course_before = runtime.get_course("alpha")
            self.assertIsNotNone(course_before)
            assert course_before is not None
            self.assertIsNone(course_before.quiz)

            _write_quiz_json(alpha_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course_after = runtime.get_course("alpha")

        self.assertIsNotNone(course_after)
        assert course_after is not None
        self.assertIsNotNone(course_after.quiz)
        loader.assert_called_once()

    def test_adding_lesson_updates_course_lessons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            alpha_dir = _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            course_before = runtime.get_course("alpha")
            self.assertIsNotNone(course_before)
            assert course_before is not None
            self.assertEqual(len(course_before.lessons), 1)

            _write_lesson(
                alpha_dir,
                "lesson_02",
                title="Second lesson",
                order=2,
            )

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                course_after = runtime.get_course("alpha")

        self.assertIsNotNone(course_after)
        assert course_after is not None
        self.assertEqual(len(course_after.lessons), 2)
        self.assertEqual(course_after.lessons[1].title, "Second lesson")
        loader.assert_called_once()

    def test_nested_file_change_triggers_single_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            alpha_dir = _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                image_path = alpha_dir / "image.jpg"
                image_path.write_bytes(b"initial")
                runtime.get_courses()
                image_path.write_bytes(b"changed-content")
                runtime.get_courses()
                runtime.get_courses()

        self.assertEqual(loader.call_count, 3)

    def test_after_auto_reload_next_call_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()
                _write_minimal_course(courses_dir, "beta", course_order=2)
                runtime.get_courses()
                runtime.get_courses()
                runtime.get_course("beta")

        self.assertEqual(loader.call_count, 2)

    def test_empty_directory_to_course_auto_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                self.assertEqual(runtime.get_courses(), [])
                _write_minimal_course(courses_dir, "alpha")
                courses = runtime.get_courses()

        self.assertEqual(loader.call_count, 2)
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].slug, "alpha")

    def test_auto_refresh_keeps_list_and_index_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            _write_minimal_course(courses_dir, "beta", course_order=2)

            courses = runtime.get_courses()
            slugs = {course.slug for course in courses}

            self.assertEqual(slugs, {"alpha", "beta"})
            self.assertIsNotNone(runtime.get_course("alpha"))
            self.assertIsNotNone(runtime.get_course("beta"))
            self.assertIsNone(runtime.get_course("missing"))

    def test_base_dir_remains_resolved_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            runtime = ContentRuntime(courses_dir)

        self.assertTrue(runtime.base_dir.is_absolute())
        self.assertEqual(runtime.base_dir, courses_dir.resolve())

    def test_consecutive_scan_errors_trigger_reload_each_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime._content_fingerprint",
                return_value=_SCAN_ERROR_FINGERPRINT,
            ):
                with patch(
                    "app.content.runtime.load_published_courses",
                    wraps=load_published_courses,
                ) as loader:
                    runtime.get_courses()
                    runtime.get_courses()
                    runtime.get_courses()
                    runtime.get_courses()

        self.assertEqual(loader.call_count, 4)

    def test_scan_error_recovery_then_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            normal_fp = _content_fingerprint(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.get_courses()

                with patch(
                    "app.content.runtime._content_fingerprint",
                    side_effect=[
                        _SCAN_ERROR_FINGERPRINT,
                        normal_fp,
                        normal_fp,
                    ],
                ):
                    runtime.get_courses()
                    runtime.get_courses()

        self.assertEqual(loader.call_count, 2)

    def test_cached_courses_count_loads_on_first_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                count = runtime.cached_courses_count()

        self.assertEqual(count, 1)
        loader.assert_called_once()

    def test_cached_courses_count_does_not_reload_when_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                runtime.cached_courses_count()
                count = runtime.cached_courses_count()

        self.assertEqual(count, 1)
        loader.assert_called_once()

    def test_cached_courses_count_ignores_disk_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            _write_minimal_course(courses_dir, "beta", course_order=2)

            with patch(
                "app.content.runtime.load_published_courses",
                wraps=load_published_courses,
            ) as loader:
                count = runtime.cached_courses_count()

        self.assertEqual(count, 1)
        loader.assert_not_called()

    def test_cached_courses_count_after_refresh_returns_new_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            _write_minimal_course(courses_dir, "beta", course_order=2)
            runtime.refresh()

            count = runtime.cached_courses_count()

        self.assertEqual(count, 2)

    def test_cached_courses_count_does_not_trigger_auto_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _write_minimal_course(courses_dir, "alpha")
            runtime = ContentRuntime(courses_dir)
            runtime.get_courses()

            with patch.object(
                runtime,
                "_ensure_fresh",
                wraps=runtime._ensure_fresh,
            ) as ensure_fresh:
                runtime.cached_courses_count()

        ensure_fresh.assert_not_called()

    def test_content_fingerprint_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            alpha_dir = _write_minimal_course(courses_dir, "alpha")
            (alpha_dir / "cover.jpg").write_bytes(b"cover")

            first = _content_fingerprint(courses_dir)
            second = _content_fingerprint(courses_dir)

        self.assertEqual(first, second)
        self.assertEqual(
            [entry[0] for entry in first],
            sorted(entry[0] for entry in first),
        )


if __name__ == "__main__":
    unittest.main()
