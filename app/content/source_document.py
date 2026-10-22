"""Intermediate representation for structured course source documents.

The IR is intentionally format-neutral and in-memory.  It preserves enough
ordered source evidence for future course composition and fidelity validation,
without coupling document extraction to generation or Web rendering.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class SourceProvenance:
    """Stable source location for one ordered intermediate element."""

    document: str
    order: int
    position: int
    page: Optional[int] = None
    slide: Optional[int] = None


@dataclass(frozen=True)
class SourceHeading:
    text: str
    level: int
    provenance: SourceProvenance


@dataclass(frozen=True)
class SourceParagraph:
    text: str
    provenance: SourceProvenance


@dataclass(frozen=True)
class SourceList:
    """One consecutive source list, preserving item order without HTML."""

    ordered: bool
    items: tuple[str, ...]
    provenance: SourceProvenance


@dataclass(frozen=True)
class SourceTable:
    """Source table cells in row-major order."""

    rows: tuple[tuple[str, ...], ...]
    provenance: SourceProvenance


@dataclass(frozen=True)
class SourceImage:
    """Raw in-memory image evidence associated with one source location."""

    asset_id: str
    content: bytes
    media_type: Optional[str]
    extension: Optional[str]
    provenance: SourceProvenance


@dataclass(frozen=True)
class SourceBoundary:
    """A page or slide boundary retained for source-to-course traceability."""

    kind: str
    provenance: SourceProvenance


SourceElement = Union[
    SourceHeading,
    SourceParagraph,
    SourceList,
    SourceTable,
    SourceImage,
    SourceBoundary,
]


@dataclass(frozen=True)
class SourceDocument:
    """Ordered, non-rendering representation of one uploaded source file."""

    name: str
    source_format: str
    elements: tuple[SourceElement, ...]


def build_source_image(
    *,
    document: str,
    content: bytes,
    provenance: SourceProvenance,
) -> SourceImage:
    """Build a deterministic in-memory source image record.

    No asset is written to disk in this step.  The ID combines a stable digest
    of the source name with the global element order, so it can later be
    associated with generated lesson assets and its source provenance.
    """
    media_type, extension = _image_metadata(content)
    document_digest = hashlib.sha256(document.encode("utf-8")).hexdigest()[:12]
    asset_id = f"source-{document_digest}-element-{provenance.order:05d}"
    return SourceImage(
        asset_id=asset_id,
        content=bytes(content),
        media_type=media_type,
        extension=extension,
        provenance=provenance,
    )


def document_name(path: Path) -> str:
    """Return the source identity used consistently in document provenance."""
    return path.name


def _image_metadata(content: bytes) -> tuple[Optional[str], Optional[str]]:
    """Describe common image data without dropping unknown embedded formats."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            image_format = (image.format or "").upper()
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError):
        return None, None

    mapping = {
        "JPEG": ("image/jpeg", ".jpg"),
        "PNG": ("image/png", ".png"),
        "WEBP": ("image/webp", ".webp"),
        "GIF": ("image/gif", ".gif"),
        "TIFF": ("image/tiff", ".tiff"),
    }
    return mapping.get(image_format, (None, None))
