"""Safe image slot uploads for tenant course content."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional


MAX_ADMIN_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_ADMIN_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


class AdminImageError(Exception):
    """Raised when an admin image cannot be validated or stored safely."""


def image_media_type(path: Path) -> str:
    """Return the response media type for one validated image path."""
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _detected_format(content: bytes) -> Optional[str]:
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def _validate_upload(filename: Optional[str], content: bytes) -> str:
    if not filename or not str(filename).strip():
        raise AdminImageError("Выберите изображение для загрузки.")
    if not content:
        raise AdminImageError("Изображение пустое.")
    if len(content) > MAX_ADMIN_IMAGE_BYTES:
        raise AdminImageError("Изображение превышает допустимый размер 10 МБ.")

    extension = Path(str(filename).replace("\\", "/")).suffix.lower()
    if extension not in SUPPORTED_ADMIN_IMAGE_EXTENSIONS:
        raise AdminImageError("Допустимые форматы изображений: JPG, PNG и WebP.")

    detected = _detected_format(content)
    expected = "jpeg" if extension in {".jpg", ".jpeg"} else extension.lstrip(".")
    if detected != expected:
        raise AdminImageError("Содержимое файла не соответствует формату изображения.")
    return extension


def replace_image_slot(
    directory: Path,
    *,
    stem: str,
    slot_filenames: Iterable[str],
    filename: Optional[str],
    content: bytes,
) -> Path:
    """Atomically replace one fixed-name image slot in an existing directory."""
    extension = _validate_upload(filename, content)
    resolved_directory = directory.resolve()
    if not resolved_directory.is_dir():
        raise AdminImageError("Каталог материала не найден.")

    target = (resolved_directory / f"{stem}{extension}").resolve()
    if target.parent != resolved_directory:
        raise AdminImageError("Недопустимый путь изображения.")

    fd, temporary_name = tempfile.mkstemp(
        dir=resolved_directory,
        prefix=f".{stem}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        for slot_filename in slot_filenames:
            candidate = resolved_directory / slot_filename
            if candidate != target and candidate.is_file():
                candidate.unlink()
        os.replace(temporary_path, target)
    except OSError as exc:
        if temporary_path.exists():
            temporary_path.unlink()
        raise AdminImageError("Не удалось сохранить изображение. Попробуйте ещё раз.") from exc
    return target


def remove_image_slot(directory: Path, *, slot_filenames: Iterable[str]) -> bool:
    """Remove every supported file occupying one image slot."""
    resolved_directory = directory.resolve()
    if not resolved_directory.is_dir():
        raise AdminImageError("Каталог материала не найден.")
    removed = False
    try:
        for slot_filename in slot_filenames:
            candidate = resolved_directory / slot_filename
            if candidate.is_file():
                candidate.unlink()
                removed = True
    except OSError as exc:
        raise AdminImageError("Не удалось удалить изображение. Попробуйте ещё раз.") from exc
    return removed
