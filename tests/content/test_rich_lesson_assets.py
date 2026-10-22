"""Tests for safe resolution of declared Rich Lesson Content v2 assets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.content.rich_lesson_assets import resolve_rich_lesson_image_asset
from app.content.rich_lesson_content import parse_rich_lesson_content
from app.content.runtime_loader import Lesson


def _lesson(directory: Path, assets: list[dict]) -> Lesson:
    return Lesson(
        path=directory,
        number=1,
        title="Lesson",
        description="",
        image_path=None,
        narration_path=None,
        content_version=2,
        rich_content=parse_rich_lesson_content(
            {
                "content_version": 2,
                "blocks": [
                    {"type": "image", "asset_id": "guide", "alt": "Guide"}
                ],
                "assets": assets,
            }
        ),
    )


class RichLessonAssetResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.lesson_dir = Path(self.tmp.name) / "lesson_01"
        (self.lesson_dir / "assets").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_resolves_only_declared_existing_image_inside_lesson_directory(self) -> None:
        image = self.lesson_dir / "assets" / "guide.webp"
        image.write_bytes(b"RIFFxxxxWEBPguide")
        lesson = _lesson(
            self.lesson_dir,
            [{"id": "guide", "file": "assets/guide.webp", "kind": "image"}],
        )

        resolved = resolve_rich_lesson_image_asset(lesson, "guide")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.path, image.resolve())
        self.assertEqual(resolved.media_type, "image/webp")
        self.assertIsNone(resolve_rich_lesson_image_asset(lesson, "not-declared"))

    def test_rejects_missing_and_unsupported_declared_files(self) -> None:
        missing = _lesson(
            self.lesson_dir,
            [{"id": "guide", "file": "assets/guide.webp", "kind": "image"}],
        )
        unsupported = _lesson(
            self.lesson_dir,
            [{"id": "guide", "file": "assets/guide.svg", "kind": "image"}],
        )

        self.assertIsNone(resolve_rich_lesson_image_asset(missing, "guide"))
        self.assertIsNone(resolve_rich_lesson_image_asset(unsupported, "guide"))

    def test_rejects_symlink_that_resolves_outside_lesson_directory(self) -> None:
        external = Path(self.tmp.name) / "outside.webp"
        external.write_bytes(b"RIFFxxxxWEBPoutside")
        (self.lesson_dir / "assets" / "guide.webp").symlink_to(external)
        lesson = _lesson(
            self.lesson_dir,
            [{"id": "guide", "file": "assets/guide.webp", "kind": "image"}],
        )

        self.assertIsNone(resolve_rich_lesson_image_asset(lesson, "guide"))


if __name__ == "__main__":
    unittest.main()
