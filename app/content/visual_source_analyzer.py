"""Deterministic preparation of source images for a future visual provider.

This module only selects and prepares ``SourceImage`` evidence.  It does not
interpret images, make network calls, or participate in course generation.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from typing import Optional

from PIL import Image, UnidentifiedImageError

from app.ai.visual_analysis_interfaces import (
    MAX_VISUAL_INPUT_BYTES,
    MAX_VISUAL_INPUTS_PER_REQUEST,
    VisualAnalysisInput,
    VisualAnalysisRequest,
)
from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceImage,
    SourceProvenance,
)
from app.content.visual_enrichment import (
    AnalysisLimitation,
    MAX_VISUAL_INPUT_DIMENSION,
    VisualInputTransform,
    build_visual_id,
    compute_content_hash,
)
from app.content.vector_image_renderer import (
    VectorImageRenderError,
    VectorImageRenderer,
    detect_legacy_vector_format,
)


VISUAL_SOURCE_ANALYZER_VERSION = 1

# Evidence storage and provider batching intentionally have separate limits.
MAX_SOURCE_IMAGES_INSPECTED = 512
MAX_TOTAL_PREPARED_BYTES_PER_DOCUMENT = 64 * 1024 * 1024
MAX_DECODE_PIXELS = 32_000_000
MIN_IMAGE_WIDTH = 64
MIN_IMAGE_HEIGHT = 64
MIN_IMAGE_PIXELS = 4_096
RESIZE_STEP_NUMERATOR = 3
RESIZE_STEP_DENOMINATOR = 4

SKIP_REASON_CODES = frozenset(
    {
        "corrupt_image",
        "decompression_bomb",
        "document_byte_limit",
        "duplicate_content",
        "input_too_large",
        "malformed_vector",
        "renderer_isolation_unavailable",
        "renderer_timeout",
        "renderer_unavailable",
        "rendered_dimensions_exceeded",
        "rendered_output_invalid",
        "rendered_output_too_large",
        "tiny_image",
        "unsupported_media_type",
        "vector_source_too_large",
    }
)

_PIL_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


@dataclass(frozen=True)
class VisualSourceSkip:
    """A deterministic, non-sensitive reason one source image was skipped."""

    source_asset_id: str
    provenance: SourceProvenance
    code: str
    canonical_source_asset_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_asset_id, str) or not self.source_asset_id:
            raise ValueError("skip source asset ID must be non-empty")
        if not isinstance(self.provenance, SourceProvenance):
            raise ValueError("skip provenance must be SourceProvenance")
        if self.code not in SKIP_REASON_CODES:
            raise ValueError("unsupported visual source skip code")
        if self.canonical_source_asset_id is not None and (
            not isinstance(self.canonical_source_asset_id, str)
            or not self.canonical_source_asset_id
        ):
            raise ValueError("skip canonical asset ID must be non-empty")


@dataclass(frozen=True)
class VisualSourcePreparation:
    """Bounded, provider-neutral requests prepared from one source document."""

    source: SourceDocument
    analyzer_version: int
    requests: tuple[VisualAnalysisRequest, ...]
    selected_visual_ids: tuple[str, ...]
    skipped: tuple[VisualSourceSkip, ...]
    limitations: tuple[AnalysisLimitation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceDocument):
            raise ValueError("preparation source must be SourceDocument")
        if self.analyzer_version != VISUAL_SOURCE_ANALYZER_VERSION:
            raise ValueError("unsupported visual source analyzer version")
        if not isinstance(self.requests, tuple):
            raise ValueError("preparation requests must be a tuple")
        if not all(isinstance(request, VisualAnalysisRequest) for request in self.requests):
            raise ValueError("preparation requests contain invalid values")
        if any(request.source != self.source for request in self.requests):
            raise ValueError("preparation requests must retain the source document")
        if not isinstance(self.selected_visual_ids, tuple) or not all(
            isinstance(value, str) for value in self.selected_visual_ids
        ):
            raise ValueError("preparation selected visual IDs must be strings")
        request_ids = tuple(
            item.visual_id for request in self.requests for item in request.inputs
        )
        if request_ids != self.selected_visual_ids:
            raise ValueError("preparation selected visual IDs must match request inputs")
        if not isinstance(self.skipped, tuple) or not all(
            isinstance(item, VisualSourceSkip) for item in self.skipped
        ):
            raise ValueError("preparation skipped values are invalid")
        if not isinstance(self.limitations, tuple) or not all(
            isinstance(item, AnalysisLimitation) for item in self.limitations
        ):
            raise ValueError("preparation limitations are invalid")


class VisualSourceAnalyzer:
    """Select source images and prepare deterministic, bounded provider batches."""

    def __init__(self, *, vector_renderer: Optional[VectorImageRenderer] = None) -> None:
        """Create an analyzer with an optional, explicitly injected renderer.

        No renderer is discovered or started automatically.  Legacy vectors are
        therefore a typed skip in normal application use until a caller supplies
        a safe, isolated renderer.
        """
        self._vector_renderer = vector_renderer

    def prepare(self, source: SourceDocument) -> VisualSourcePreparation:
        if not isinstance(source, SourceDocument):
            raise ValueError("source must be a SourceDocument")

        requests_inputs: list[VisualAnalysisInput] = []
        skipped: list[VisualSourceSkip] = []
        limitations = _unavailable_render_limitations(source)
        seen_hashes: dict[str, SourceImage] = {}
        total_prepared_bytes = 0
        source_images = sorted(
            (element for element in source.elements if isinstance(element, SourceImage)),
            key=lambda image: image.provenance.order,
        )

        for index, source_image in enumerate(source_images):
            if index >= MAX_SOURCE_IMAGES_INSPECTED:
                limitations.append(
                    AnalysisLimitation(
                        "input_truncated",
                        "Additional source images were not inspected by analyzer version 1.",
                    )
                )
                break

            source_hash = compute_content_hash(source_image.content)
            canonical = seen_hashes.get(source_hash)
            if canonical is not None:
                skipped.append(
                    VisualSourceSkip(
                        source_asset_id=source_image.asset_id,
                        provenance=source_image.provenance,
                        code="duplicate_content",
                        canonical_source_asset_id=canonical.asset_id,
                    )
                )
                continue
            seen_hashes[source_hash] = source_image

            prepared, reason = _prepare_source_image(
                source_image,
                vector_renderer=self._vector_renderer,
            )
            if prepared is None:
                skipped.append(
                    VisualSourceSkip(
                        source_asset_id=source_image.asset_id,
                        provenance=source_image.provenance,
                        code=reason or "corrupt_image",
                    )
                )
                continue
            if total_prepared_bytes + len(prepared.content) > MAX_TOTAL_PREPARED_BYTES_PER_DOCUMENT:
                skipped.append(
                    VisualSourceSkip(
                        source_asset_id=source_image.asset_id,
                        provenance=source_image.provenance,
                        code="document_byte_limit",
                    )
                )
                continue

            visual_id = build_visual_id(
                source,
                input_kind="source_image",
                provenance=source_image.provenance,
                source_content_hash=source_hash,
                source_asset_id=source_image.asset_id,
            )
            requests_inputs.append(
                VisualAnalysisInput(
                    visual_id=visual_id,
                    source_asset_id=source_image.asset_id,
                    provenance=source_image.provenance,
                    input_kind="source_image",
                    source_content_hash=source_hash,
                    input_content_hash=compute_content_hash(prepared.content),
                    media_type=prepared.media_type,
                    content=prepared.content,
                    transform=prepared.transform,
                )
            )
            total_prepared_bytes += len(prepared.content)

        batches = tuple(
            VisualAnalysisRequest(source=source, inputs=tuple(requests_inputs[start : start + MAX_VISUAL_INPUTS_PER_REQUEST]))
            for start in range(0, len(requests_inputs), MAX_VISUAL_INPUTS_PER_REQUEST)
        )
        return VisualSourcePreparation(
            source=source,
            analyzer_version=VISUAL_SOURCE_ANALYZER_VERSION,
            requests=batches,
            selected_visual_ids=tuple(item.visual_id for item in requests_inputs),
            skipped=tuple(skipped),
            limitations=tuple(limitations),
        )


@dataclass(frozen=True)
class _PreparedSourceImage:
    content: bytes
    media_type: str
    transform: Optional[VisualInputTransform]


def _prepare_source_image(
    source_image: SourceImage,
    *,
    vector_renderer: Optional[VectorImageRenderer],
) -> tuple[Optional[_PreparedSourceImage], Optional[str]]:
    vector_format = detect_legacy_vector_format(source_image.content)
    if vector_format is not None:
        return _prepare_legacy_vector_image(
            source_image,
            source_format=vector_format,
            vector_renderer=vector_renderer,
        )
    return _prepare_native_source_image(source_image)


def _prepare_legacy_vector_image(
    source_image: SourceImage,
    *,
    source_format: str,
    vector_renderer: Optional[VectorImageRenderer],
) -> tuple[Optional[_PreparedSourceImage], Optional[str]]:
    """Convert declared vector evidence only for the bounded provider input."""
    if vector_renderer is None:
        return None, "renderer_unavailable"
    try:
        rendered = vector_renderer.render_png(
            source_image.content,
            source_format=source_format,
        )
    except VectorImageRenderError as error:
        return None, error.code

    if not isinstance(rendered, bytes) or not rendered:
        return None, "rendered_output_invalid"
    # Reject oversized renderer output before decoding it.  This is both a
    # resource bound and a deliberately privacy-neutral failure path.
    if len(rendered) > MAX_VISUAL_INPUT_BYTES:
        return None, "rendered_output_too_large"
    return _prepare_rendered_vector_png(rendered, source_format=source_format)


def _prepare_rendered_vector_png(
    rendered: bytes,
    *,
    source_format: str,
) -> tuple[Optional[_PreparedSourceImage], Optional[str]]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(rendered)) as opened:
                if (opened.format or "").upper() != "PNG":
                    return None, "rendered_output_invalid"
                width, height = opened.size
                if width * height > MAX_DECODE_PIXELS:
                    return None, "rendered_dimensions_exceeded"
                if (
                    width < MIN_IMAGE_WIDTH
                    or height < MIN_IMAGE_HEIGHT
                    or width * height < MIN_IMAGE_PIXELS
                ):
                    return None, "rendered_output_invalid"
                image = opened.copy()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return None, "rendered_output_invalid"

    if max(width, height) > MAX_VISUAL_INPUT_DIMENSION:
        return None, "rendered_dimensions_exceeded"

    return (
        _PreparedSourceImage(
            content=rendered,
            media_type="image/png",
            transform=VisualInputTransform(
                version=2,
                resize_mode="none",
                max_dimension=None,
                output_media_type="image/png",
                vector_conversion=f"{source_format}_to_png",
            ),
        ),
        None,
    )


def _prepare_native_source_image(
    source_image: SourceImage,
) -> tuple[Optional[_PreparedSourceImage], Optional[str]]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(source_image.content)) as opened:
                image_format = (opened.format or "").upper()
                metadata = _PIL_FORMATS.get(image_format)
                if metadata is None:
                    return None, "unsupported_media_type"
                media_type, extension = metadata
                if source_image.media_type != media_type or source_image.extension != extension:
                    return None, "unsupported_media_type"
                width, height = opened.size
                if width * height > MAX_DECODE_PIXELS:
                    return None, "decompression_bomb"
                if (
                    width < MIN_IMAGE_WIDTH
                    or height < MIN_IMAGE_HEIGHT
                    or width * height < MIN_IMAGE_PIXELS
                ):
                    return None, "tiny_image"
                image = opened.copy()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return None, "corrupt_image"

    if (
        max(width, height) <= MAX_VISUAL_INPUT_DIMENSION
        and len(source_image.content) <= MAX_VISUAL_INPUT_BYTES
    ):
        return _PreparedSourceImage(source_image.content, media_type, None), None

    target_dimension = min(max(width, height), MAX_VISUAL_INPUT_DIMENSION)
    while target_dimension >= max(MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT):
        content, output_media_type = _encode_contained(image, target_dimension)
        if len(content) <= MAX_VISUAL_INPUT_BYTES:
            return (
                _PreparedSourceImage(
                    content=content,
                    media_type=output_media_type,
                    transform=VisualInputTransform(
                        version=1,
                        resize_mode="contain",
                        max_dimension=target_dimension,
                        output_media_type=output_media_type,
                    ),
                ),
                None,
            )
        next_dimension = max(
            max(MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT),
            (target_dimension * RESIZE_STEP_NUMERATOR) // RESIZE_STEP_DENOMINATOR,
        )
        if next_dimension == target_dimension:
            break
        target_dimension = next_dimension
    return None, "input_too_large"


def _encode_contained(image: Image.Image, target_dimension: int) -> tuple[bytes, str]:
    contained = image.copy()
    contained.thumbnail((target_dimension, target_dimension), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    if _has_alpha(contained):
        contained.convert("RGBA").save(output, format="PNG", compress_level=9)
        return output.getvalue(), "image/png"
    contained.convert("RGB").save(
        output,
        format="JPEG",
        quality=85,
        optimize=False,
        progressive=False,
    )
    return output.getvalue(), "image/jpeg"


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _unavailable_render_limitations(source: SourceDocument) -> list[AnalysisLimitation]:
    limitations: list[AnalysisLimitation] = []
    boundary_kinds = {
        element.kind
        for element in source.elements
        if isinstance(element, SourceBoundary)
    }
    if "page_break" in boundary_kinds:
        limitations.append(
            AnalysisLimitation(
                "unsupported_format",
                "PDF page rendering is not available in analyzer version 1.",
            )
        )
    if "slide_boundary" in boundary_kinds:
        limitations.append(
            AnalysisLimitation(
                "unsupported_format",
                "PPTX slide rendering is not available in analyzer version 1.",
            )
        )
    return limitations
