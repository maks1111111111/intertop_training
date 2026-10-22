"""Provider-neutral contracts for future visual source analysis.

The interfaces are intentionally isolated from the existing text-only
``AIClient`` and do not make network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.content.source_document import SourceDocument, SourceProvenance
from app.content.visual_enrichment import (
    EnrichedSourceDocument,
    INPUT_KINDS,
    VisualInputTransform,
    VISION_MEDIA_TYPES,
    _ASSET_ID_PATTERN,
    _VISUAL_ID_PATTERN,
    _validate_content_hash,
    _validate_enum,
    _validate_identifier,
    compute_content_hash,
    validate_visual_reference,
)


MAX_VISUAL_INPUTS_PER_REQUEST = 16
MAX_VISUAL_INPUT_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class VisualAnalysisInput:
    """One in-memory image input, with no URL or filesystem-path field."""

    visual_id: str
    source_asset_id: str | None
    provenance: SourceProvenance
    input_kind: str
    source_content_hash: str
    input_content_hash: str
    media_type: str
    content: bytes
    transform: VisualInputTransform | None = None

    def __post_init__(self) -> None:
        _validate_identifier("visual ID", self.visual_id, _VISUAL_ID_PATTERN)
        if self.source_asset_id is not None:
            _validate_identifier("source asset ID", self.source_asset_id, _ASSET_ID_PATTERN)
        if not isinstance(self.provenance, SourceProvenance):
            raise ValueError("visual input provenance must be SourceProvenance")
        _validate_enum("input kind", self.input_kind, INPUT_KINDS)
        _validate_content_hash(self.source_content_hash)
        _validate_content_hash(self.input_content_hash)
        if self.media_type not in VISION_MEDIA_TYPES:
            raise ValueError("unsupported visual input media type")
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("visual input content must be non-empty bytes")
        if len(self.content) > MAX_VISUAL_INPUT_BYTES:
            raise ValueError("visual input exceeds maximum bytes")
        if self.input_content_hash != compute_content_hash(self.content):
            raise ValueError("visual input content hash does not match input bytes")
        if self.transform is not None:
            if not isinstance(self.transform, VisualInputTransform):
                raise ValueError("visual input transform is invalid")
            if self.transform.output_media_type != self.media_type:
                raise ValueError("visual input media type must match transform output")
        elif self.source_content_hash != self.input_content_hash:
            raise ValueError("transformed visual input requires transform metadata")


@dataclass(frozen=True)
class VisualAnalysisRequest:
    """A bounded request for a future visual-analysis provider."""

    source: SourceDocument
    inputs: tuple[VisualAnalysisInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceDocument):
            raise ValueError("visual analysis request source must be SourceDocument")
        if not isinstance(self.inputs, tuple) or not self.inputs:
            raise ValueError("visual analysis request requires input tuple")
        if len(self.inputs) > MAX_VISUAL_INPUTS_PER_REQUEST:
            raise ValueError("visual analysis request exceeds maximum inputs")
        if not all(isinstance(item, VisualAnalysisInput) for item in self.inputs):
            raise ValueError("visual analysis request contains invalid input")
        visual_ids: set[str] = set()
        for item in self.inputs:
            if item.visual_id in visual_ids:
                raise ValueError("visual analysis request input IDs must be unique")
            visual_ids.add(item.visual_id)
            validate_visual_reference(
                self.source,
                visual_id=item.visual_id,
                source_asset_id=item.source_asset_id,
                provenance=item.provenance,
                input_kind=item.input_kind,
                source_content_hash=item.source_content_hash,
            )


@dataclass(frozen=True)
class VisualAnalysisResponse:
    """Validated response envelope returned by a visual-analysis provider."""

    enriched_document: EnrichedSourceDocument

    def __post_init__(self) -> None:
        if not isinstance(self.enriched_document, EnrichedSourceDocument):
            raise ValueError("visual analysis response requires EnrichedSourceDocument")


class VisualAnalysisClient(Protocol):
    """A future provider that analyzes visual source evidence."""

    def analyze(self, request: VisualAnalysisRequest) -> VisualAnalysisResponse:
        """Return structured visual observations for one bounded request."""
        ...


@dataclass
class FakeVisualAnalysisClient:
    """Small recording fake for contract and future orchestration tests."""

    response: VisualAnalysisResponse
    requests: list[VisualAnalysisRequest] = field(default_factory=list)

    def analyze(self, request: VisualAnalysisRequest) -> VisualAnalysisResponse:
        self.requests.append(request)
        return self.response
