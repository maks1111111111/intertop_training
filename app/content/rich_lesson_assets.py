"""Safe resolution of declared Rich Lesson Content v2 image assets.

The resolver deliberately accepts a runtime ``Lesson`` and an asset ID, never
a client supplied file path.  It returns only a regular image file that remains
inside the lesson directory after canonical resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from app.content.contract import LESSON_IMAGE_EXTENSIONS
from app.content.runtime_loader import Lesson


@dataclass(frozen=True)
class ResolvedRichLessonImageAsset:
    """A safe, declared image file ready for a private response."""

    path: Path
    media_type: str


def resolve_rich_lesson_image_asset(
    lesson: Lesson,
    asset_id: str,
) -> Optional[ResolvedRichLessonImageAsset]:
    """Return one declared, safely-contained v2 image asset, if available.

    ``asset_id`` is looked up only against validated rich-content metadata.
    The metadata parser already limits ``file`` to ``assets/...`` POSIX paths;
    canonical containment here is the defence-in-depth check for on-disk
    changes and symbolic links after the course was loaded.
    """
    rich_content = lesson.rich_content
    if rich_content is None or not isinstance(asset_id, str):
        return None

    asset = next(
        (item for item in rich_content.assets if item.id == asset_id),
        None,
    )
    if asset is None or asset.kind != "image":
        return None

    asset_file = PurePosixPath(asset.file)
    if asset_file.suffix.lower() not in LESSON_IMAGE_EXTENSIONS:
        return None

    try:
        lesson_directory = lesson.path.resolve(strict=True)
        if not lesson_directory.is_dir():
            return None
        candidate = (lesson_directory / Path(*asset_file.parts)).resolve(strict=True)
        candidate.relative_to(lesson_directory)
    except (OSError, RuntimeError, ValueError):
        return None

    if not candidate.is_file():
        return None
    media_type = _image_media_type(candidate)
    if media_type is None:
        return None
    return ResolvedRichLessonImageAsset(path=candidate, media_type=media_type)


def _image_media_type(path: Path) -> Optional[str]:
    """Return an allow-listed image type for one validated v2 asset path."""
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return None
