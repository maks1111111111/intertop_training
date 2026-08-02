"""Tests for the Content Validator CLI (``app.content.cli``)."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ai.interfaces import GeneratedCourseMetadata, LessonGenerationResult
from app.content.cli import _DEFAULT_COURSES_DIR, main
from app.content.course_writer import CourseDraft
from app.content.lesson_builder import LessonCandidate


def _create_valid_course(courses_dir: Path, slug: str = "valid") -> Path:
    """Create a minimal course that passes structural validation."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text("{}", encoding="utf-8")
    lesson_dir = course_dir / "lesson_01"
    lesson_dir.mkdir()
    (lesson_dir / "lesson.json").write_text("{}", encoding="utf-8")
    return course_dir


def _create_course_with_warning(courses_dir: Path, slug: str = "warning") -> Path:
    """Create a course that triggers a warning but no errors."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text("{}", encoding="utf-8")
    return course_dir


def _create_course_with_duplicate_order(
    courses_dir: Path,
    slug: str = "error",
) -> Path:
    """Create a course with duplicate lesson order values."""
    course_dir = courses_dir / slug
    course_dir.mkdir()
    (course_dir / "course.json").write_text("{}", encoding="utf-8")
    for lesson_slug in ("lesson_01", "lesson_02"):
        lesson_dir = course_dir / lesson_slug
        lesson_dir.mkdir()
        (lesson_dir / "lesson.json").write_text(
            '{"order": 1}',
            encoding="utf-8",
        )
    return course_dir


def _run_cli(courses_dir: Path) -> tuple[int, str]:
    """Run the CLI against ``courses_dir`` and capture stdout."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = main([str(courses_dir)])
    return exit_code, stdout.getvalue()


def _run_generate_cli(document_path: Path) -> tuple[int, str]:
    """Run the generate subcommand and capture stdout."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = main(["generate", str(document_path)])
    return exit_code, stdout.getvalue()


class ContentCliTests(unittest.TestCase):
    """Integration tests for ``app.content.cli.main``."""

    @patch("app.content.cli.load_project_env")
    def test_main_loads_project_env(self, mock_load_project_env: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _run_cli(courses_dir)

        mock_load_project_env.assert_called_once_with()

    def test_empty_courses_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Summary:", output)
        self.assertIn("Courses: 0", output)
        self.assertIn("Errors: 0", output)
        self.assertIn("Warnings: 0", output)

    def test_missing_courses_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = Path(tmp) / "missing"
            exit_code, output = _run_cli(missing_dir)

        self.assertEqual(exit_code, 2)
        self.assertIn("does not exist or is not a directory", output)

    def test_valid_course_without_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_valid_course(courses_dir, slug="valid")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Course: valid", output)
        self.assertIn("Status: READY", output)
        self.assertRegex(
            output,
            r"Course: valid\nStatus: READY\nErrors: 0\nWarnings: 0",
        )
        self.assertIn("Courses: 1", output)
        self.assertIn("Errors: 0", output)
        self.assertIn("Warnings: 0", output)

    def test_course_with_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course_with_warning(courses_dir, slug="warning")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("WARNING", output)
        self.assertIn("course_without_lessons", output)
        self.assertIn("Status: READY", output)
        course_section = output.split("Course: warning", 1)[1].split("\n\n", 1)[0]
        self.assertIn("Status: READY", course_section)
        self.assertIn("Errors: 0", course_section)
        self.assertIn("Warnings: 1", course_section)
        self.assertIn("Courses: 1", output)
        self.assertIn("Errors: 0", output)
        self.assertRegex(output, r"Warnings: [1-9]\d*")

    def test_course_with_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course_with_duplicate_order(courses_dir, slug="error")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 1)
        self.assertIn("ERROR [duplicate_lesson_order]", output)
        self.assertIn("Status: NOT READY", output)
        course_section = output.split("Course: error", 1)[1].split("\n\n", 1)[0]
        self.assertIn("Status: NOT READY", course_section)
        self.assertIn("Errors: 1", course_section)
        self.assertIn("Warnings: 0", course_section)
        self.assertIn("Courses: 1", output)
        self.assertRegex(output, r"Errors: [1-9]\d*")

    def test_release_status_ready_without_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_valid_course(courses_dir, slug="ready")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertRegex(
            output,
            r"Course: ready\nStatus: READY\nErrors: 0\nWarnings: 0\n",
        )

    def test_release_status_ready_with_warnings_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course_with_warning(courses_dir, slug="warn_only")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Status: READY", output)
        self.assertRegex(output, r"Errors: 0\nWarnings: 1")

    def test_release_status_not_ready_with_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_course_with_duplicate_order(courses_dir, slug="not_ready")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 1)
        self.assertIn("Status: NOT READY", output)
        self.assertRegex(output, r"Errors: 1\nWarnings: 0")

    def test_deterministic_course_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp)
            _create_valid_course(courses_dir, slug="z_course")
            _create_valid_course(courses_dir, slug="a_course")
            exit_code, output = _run_cli(courses_dir)

        self.assertEqual(exit_code, 0)
        a_index = output.index("Course: a_course")
        z_index = output.index("Course: z_course")
        self.assertLess(a_index, z_index)


class GenerateCliTests(unittest.TestCase):
    """Tests for the ``generate`` CLI subcommand."""

    @patch("app.content.cli.CourseFileWriter")
    @patch("app.content.cli.CourseWriter")
    @patch("app.content.cli.create_imported_text_generation_service")
    @patch("app.content.cli.CourseImporter")
    def test_generate_calls_importer_and_bootstrap(
        self,
        mock_importer_class: MagicMock,
        mock_create_service: MagicMock,
        mock_writer_class: MagicMock,
        mock_file_writer_class: MagicMock,
    ) -> None:
        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer
        mock_importer.read_source.return_value = "imported text"

        mock_service = MagicMock()
        mock_create_service.return_value = mock_service
        generation_result = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="First lesson",
                    content="Content one.",
                ),
                LessonCandidate(
                    title="Second lesson",
                    content="Content two.",
                ),
            ],
            course=GeneratedCourseMetadata(
                language="ru",
                title="Safety Training",
                description="Introductory safety course.",
            ),
        )
        mock_service.generate_from_text.return_value = generation_result

        draft = CourseDraft(
            slug="safety-training",
            title="Safety Training",
            description="Introductory safety course.",
            language="ru",
            lessons=tuple(generation_result.lessons),
        )
        mock_writer = MagicMock()
        mock_writer_class.return_value = mock_writer
        mock_writer.write.return_value = draft

        course_dir = _DEFAULT_COURSES_DIR / "safety-training"
        mock_file_writer = MagicMock()
        mock_file_writer_class.return_value = mock_file_writer
        mock_file_writer.write.return_value = course_dir

        with tempfile.TemporaryDirectory() as tmp:
            document_path = Path(tmp) / "course.pdf"
            document_path.write_text("dummy", encoding="utf-8")
            exit_code, output = _run_generate_cli(document_path)

        self.assertEqual(exit_code, 0)
        mock_importer_class.assert_called_once_with()
        mock_importer.read_source.assert_called_once_with(document_path)
        mock_create_service.assert_called_once_with()
        mock_service.generate_from_text.assert_called_once_with(
            "imported text",
        )
        mock_writer_class.assert_called_once_with()
        mock_writer.write.assert_called_once_with(generation_result)
        mock_file_writer_class.assert_called_once_with()
        mock_file_writer.write.assert_called_once_with(
            draft,
            _DEFAULT_COURSES_DIR / "safety-training",
        )
        self.assertIn("Generated course:", output)
        self.assertIn(str(course_dir.resolve()), output)
        self.assertIn("Lessons:", output)
        self.assertIn("1. First lesson", output)
        self.assertIn("2. Second lesson", output)

    @patch("app.content.cli.create_imported_text_generation_service")
    @patch("app.content.cli.CourseImporter")
    def test_generate_persists_course_to_disk(
        self,
        mock_importer_class: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        mock_importer = MagicMock()
        mock_importer_class.return_value = mock_importer
        mock_importer.read_source.return_value = "Section one\n\nSection two"

        mock_service = MagicMock()
        mock_create_service.return_value = mock_service
        mock_service.generate_from_text.return_value = LessonGenerationResult(
            lessons=[
                LessonCandidate(
                    title="Section 1",
                    content="Section one body.",
                ),
                LessonCandidate(
                    title="Section 2",
                    content="Section two body.",
                ),
            ],
            course=GeneratedCourseMetadata(
                language="en",
                title="Imported Course",
                description="Generated from document.",
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            courses_dir = Path(tmp) / "courses"
            courses_dir.mkdir()

            document_path = Path(tmp) / "course.pdf"
            document_path.write_text("dummy", encoding="utf-8")

            with patch("app.content.cli._DEFAULT_COURSES_DIR", courses_dir):
                exit_code, output = _run_generate_cli(document_path)

            course_dir = courses_dir / "imported-course"
            self.assertEqual(exit_code, 0)
            self.assertTrue(course_dir.is_dir())
            self.assertTrue((course_dir / "course.json").is_file())
            self.assertTrue((course_dir / "lesson_01" / "lesson.json").is_file())
            self.assertTrue((course_dir / "lesson_02" / "lesson.json").is_file())
            self.assertIn("Generated course:", output)
            self.assertIn(str(course_dir.resolve()), output)
            self.assertIn("1. Section 1", output)
            self.assertIn("2. Section 2", output)

    @patch("app.content.cli.create_imported_text_generation_service")
    @patch("app.content.cli.CourseImporter")
    def test_generate_missing_document(
        self,
        mock_importer_class: MagicMock,
        mock_create_service: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "missing.pdf"
            exit_code, output = _run_generate_cli(missing_path)

        self.assertEqual(exit_code, 2)
        self.assertIn("does not exist or is not a file", output)
        mock_importer_class.assert_not_called()
        mock_create_service.assert_not_called()


if __name__ == "__main__":
    unittest.main()
