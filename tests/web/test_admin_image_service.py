"""Tests for safe fixed-slot course and lesson image uploads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.web.admin_image_service import (
    AdminImageError,
    image_media_type,
    remove_image_slot,
    replace_image_slot,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image"
JPEG_BYTES = b"\xff\xd8\xff" + b"test-image"


class AdminImageServiceTests(unittest.TestCase):
    """Validate image signatures, fixed names, replacement, and removal."""

    def test_replace_image_slot_writes_fixed_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            result = replace_image_slot(
                directory,
                stem="cover",
                slot_filenames=("cover.jpg", "cover.png", "cover.webp"),
                filename="uploaded.png",
                content=PNG_BYTES,
            )

            self.assertEqual(result, (directory / "cover.png").resolve())
            self.assertEqual(result.read_bytes(), PNG_BYTES)
            self.assertEqual(result.stat().st_mode & 0o777, 0o640)
            self.assertEqual(image_media_type(result), "image/png")

    def test_replace_image_slot_removes_previous_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            old_path = directory / "image.jpg"
            old_path.write_bytes(JPEG_BYTES)

            result = replace_image_slot(
                directory,
                stem="image",
                slot_filenames=("image.jpg", "image.png", "image.webp"),
                filename="new.png",
                content=PNG_BYTES,
            )

            self.assertFalse(old_path.exists())
            self.assertEqual(result.name, "image.png")

    def test_replace_image_slot_rejects_extension_signature_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                AdminImageError,
                "не соответствует формату",
            ):
                replace_image_slot(
                    Path(tmp),
                    stem="cover",
                    slot_filenames=("cover.jpg", "cover.png"),
                    filename="fake.jpg",
                    content=PNG_BYTES,
                )

    def test_remove_image_slot_removes_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "image.webp"
            path.write_bytes(b"RIFFxxxxWEBPdata")

            removed = remove_image_slot(
                directory,
                slot_filenames=("image.jpg", "image.png", "image.webp"),
            )

            self.assertTrue(removed)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
