"""Validated, non-rendering visual enrichment contracts for source documents.

This module is deliberately separate from document reading, generation, and Web
rendering.  It stores typed observations that a future visual-analysis provider
can derive from a :class:`SourceDocument`; it never contains HTML, URLs, file
paths, or executable content.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceImage,
    SourceProvenance,
)


ENRICHMENT_ANALYSIS_VERSION = 1

# This is evidence storage capacity, not the provider batch size.  A source
# document can contain hundreds of screenshots even though future provider
# requests must remain small and bounded.
MAX_ANALYSES_PER_DOCUMENT = 512
MAX_LIMITATIONS_PER_SCOPE = 16
MAX_DETECTED_TEXT_ITEMS = 32
MAX_SECTIONS_PER_ANALYSIS = 24
MAX_TABLES_PER_ANALYSIS = 8
MAX_UI_CONTROLS_PER_ANALYSIS = 50
MAX_DIAGRAMS_PER_ANALYSIS = 8
MAX_TABLE_COLUMNS = 20
MAX_TABLE_ROWS = 100
MAX_DIAGRAM_NODES = 64
MAX_DIAGRAM_EDGES = 128

MAX_SHORT_TEXT_LENGTH = 400
MAX_DESCRIPTION_LENGTH = 4_000
MAX_DETECTED_TEXT_LENGTH = 2_000
MAX_SECTION_TEXT_LENGTH = 6_000
MAX_TABLE_CELL_LENGTH = 1_000
MAX_LIMITATION_DETAIL_LENGTH = 500
MAX_VISUAL_INPUT_DIMENSION = 4_096

INPUT_KINDS = frozenset({"source_image", "page_render", "slide_render"})
VISION_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
INPUT_TRANSFORM_VERSIONS = frozenset({1})
INPUT_RESIZE_MODES = frozenset({"none", "contain"})
UI_CONTROL_KINDS = frozenset(
    {"button", "input", "select", "checkbox", "tab", "menu_item", "link", "label", "other"}
)
DIAGRAM_KINDS = frozenset(
    {"classification", "flow", "hierarchy", "comparison", "other"}
)
DIAGRAM_NODE_KINDS = frozenset(
    {"concept", "category", "process_step", "decision", "other"}
)
DIAGRAM_EDGE_KINDS = frozenset(
    {"contains", "flows_to", "relates_to", "contrasts_with", "other"}
)
LIMITATION_CODES = frozenset(
    {
        "input_truncated",
        "text_unreadable",
        "low_confidence",
        "unsupported_format",
        "layout_ambiguous",
        "image_unavailable",
        "analysis_failed",
    }
)

_CONTENT_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_VISUAL_ID_PATTERN = re.compile(r"^visual-[a-f0-9]{32}$")
_ASSET_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
_NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_UNSAFE_TEXT_MARKERS = ("<", ">", "http://", "https://", "file://", "data:", "javascript:")


@dataclass(frozen=True)
class AnalysisLimitation:
    """A bounded, allow-listed limitation of one visual observation."""

    code: str
    detail: str

    def __post_init__(self) -> None:
        _validate_enum("limitation code", self.code, LIMITATION_CODES)
        _validate_plain_text(
            "limitation detail",
            self.detail,
            maximum=MAX_LIMITATION_DETAIL_LENGTH,
        )


@dataclass(frozen=True)
class VisualInputTransform:
    """Bounded metadata for a non-identity provider-input representation.

    It records a safe resize/re-encode representation without changing the
    identity of the immutable source evidence.
    """

    version: int
    resize_mode: str
    max_dimension: Optional[int]
    output_media_type: str

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version not in INPUT_TRANSFORM_VERSIONS:
            raise ValueError("unsupported visual input transform version")
        if self.resize_mode not in INPUT_RESIZE_MODES:
            raise ValueError("unsupported visual input resize mode")
        if self.output_media_type not in VISION_MEDIA_TYPES:
            raise ValueError("unsupported visual input transform media type")
        if self.resize_mode == "none":
            if self.max_dimension is not None:
                raise ValueError("unresized visual input must not set max dimension")
            return
        if (
            isinstance(self.max_dimension, bool)
            or not isinstance(self.max_dimension, int)
            or not 1 <= self.max_dimension <= MAX_VISUAL_INPUT_DIMENSION
        ):
            raise ValueError("visual input transform max dimension is invalid")


@dataclass(frozen=True)
class VisualSection:
    """A text section visibly detected in an image or page render."""

    title: str
    text: str
    level: int

    def __post_init__(self) -> None:
        _validate_plain_text("section title", self.title, maximum=MAX_SHORT_TEXT_LENGTH)
        _validate_plain_text(
            "section text",
            self.text,
            maximum=MAX_SECTION_TEXT_LENGTH,
            allow_empty=True,
        )
        if isinstance(self.level, bool) or not isinstance(self.level, int):
            raise ValueError("section level must be an integer")
        if self.level < 1 or self.level > 6:
            raise ValueError("section level must be between 1 and 6")


@dataclass(frozen=True)
class VisualTable:
    """A visible table represented only as bounded, plain-text cells."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        _validate_tuple("table columns", self.columns, maximum=MAX_TABLE_COLUMNS)
        if not self.columns:
            raise ValueError("table columns must not be empty")
        for column in self.columns:
            _validate_plain_text("table column", column, maximum=MAX_TABLE_CELL_LENGTH)

        _validate_tuple("table rows", self.rows, maximum=MAX_TABLE_ROWS)
        for row in self.rows:
            if not isinstance(row, tuple):
                raise ValueError("each table row must be a tuple")
            if len(row) != len(self.columns):
                raise ValueError("each table row must match the number of columns")
            for cell in row:
                _validate_plain_text(
                    "table cell",
                    cell,
                    maximum=MAX_TABLE_CELL_LENGTH,
                    allow_empty=True,
                )


@dataclass(frozen=True)
class VisualUIControl:
    """A visible UI control, without any target URL or executable behavior."""

    kind: str
    label: str
    state: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_enum("UI control kind", self.kind, UI_CONTROL_KINDS)
        _validate_plain_text("UI control label", self.label, maximum=MAX_SHORT_TEXT_LENGTH)
        if self.state is not None:
            _validate_plain_text(
                "UI control state",
                self.state,
                maximum=MAX_SHORT_TEXT_LENGTH,
            )


@dataclass(frozen=True)
class DiagramNode:
    """A semantic node from a visible diagram."""

    node_id: str
    label: str
    kind: str

    def __post_init__(self) -> None:
        _validate_identifier("diagram node ID", self.node_id, _NODE_ID_PATTERN)
        _validate_plain_text("diagram node label", self.label, maximum=MAX_SHORT_TEXT_LENGTH)
        _validate_enum("diagram node kind", self.kind, DIAGRAM_NODE_KINDS)


@dataclass(frozen=True)
class DiagramEdge:
    """An allow-listed relationship between two diagram nodes."""

    source_node_id: str
    target_node_id: str
    kind: str
    label: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_identifier("diagram edge source", self.source_node_id, _NODE_ID_PATTERN)
        _validate_identifier("diagram edge target", self.target_node_id, _NODE_ID_PATTERN)
        if self.source_node_id == self.target_node_id:
            raise ValueError("diagram edge must connect distinct nodes")
        _validate_enum("diagram edge kind", self.kind, DIAGRAM_EDGE_KINDS)
        if self.label is not None:
            _validate_plain_text(
                "diagram edge label",
                self.label,
                maximum=MAX_SHORT_TEXT_LENGTH,
            )


@dataclass(frozen=True)
class VisualDiagram:
    """A bounded graph description of a visible source diagram."""

    kind: str
    summary: str
    nodes: tuple[DiagramNode, ...]
    edges: tuple[DiagramEdge, ...]

    def __post_init__(self) -> None:
        _validate_enum("diagram kind", self.kind, DIAGRAM_KINDS)
        _validate_plain_text("diagram summary", self.summary, maximum=MAX_DESCRIPTION_LENGTH)
        _validate_tuple("diagram nodes", self.nodes, maximum=MAX_DIAGRAM_NODES)
        if not self.nodes:
            raise ValueError("diagram nodes must not be empty")
        if not all(isinstance(node, DiagramNode) for node in self.nodes):
            raise ValueError("diagram nodes must contain DiagramNode values")
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("diagram node IDs must be unique")

        _validate_tuple("diagram edges", self.edges, maximum=MAX_DIAGRAM_EDGES)
        if not all(isinstance(edge, DiagramEdge) for edge in self.edges):
            raise ValueError("diagram edges must contain DiagramEdge values")
        for edge in self.edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                raise ValueError("diagram edges must reference declared nodes")


@dataclass(frozen=True)
class VisualAnalysis:
    """Validated visual observations tied to one original source location."""

    visual_id: str
    source_asset_id: Optional[str]
    provenance: SourceProvenance
    input_kind: str
    source_content_hash: str
    input_content_hash: str
    description: str
    detected_text: tuple[str, ...] = ()
    sections: tuple[VisualSection, ...] = ()
    tables: tuple[VisualTable, ...] = ()
    ui_controls: tuple[VisualUIControl, ...] = ()
    diagrams: tuple[VisualDiagram, ...] = ()
    confidence: Optional[float] = None
    limitations: tuple[AnalysisLimitation, ...] = ()
    input_transform: Optional[VisualInputTransform] = None

    def __post_init__(self) -> None:
        _validate_identifier("visual ID", self.visual_id, _VISUAL_ID_PATTERN)
        if self.source_asset_id is not None:
            _validate_identifier("source asset ID", self.source_asset_id, _ASSET_ID_PATTERN)
        if not isinstance(self.provenance, SourceProvenance):
            raise ValueError("visual analysis provenance must be SourceProvenance")
        _validate_enum("input kind", self.input_kind, INPUT_KINDS)
        _validate_content_hash(self.source_content_hash)
        _validate_content_hash(self.input_content_hash)
        _validate_plain_text("visual description", self.description, maximum=MAX_DESCRIPTION_LENGTH)
        _validate_plain_text_tuple(
            "detected text",
            self.detected_text,
            maximum_items=MAX_DETECTED_TEXT_ITEMS,
            maximum_text=MAX_DETECTED_TEXT_LENGTH,
        )
        _validate_typed_tuple(
            "visual sections",
            self.sections,
            VisualSection,
            maximum=MAX_SECTIONS_PER_ANALYSIS,
        )
        _validate_typed_tuple(
            "visual tables",
            self.tables,
            VisualTable,
            maximum=MAX_TABLES_PER_ANALYSIS,
        )
        _validate_typed_tuple(
            "visual UI controls",
            self.ui_controls,
            VisualUIControl,
            maximum=MAX_UI_CONTROLS_PER_ANALYSIS,
        )
        _validate_typed_tuple(
            "visual diagrams",
            self.diagrams,
            VisualDiagram,
            maximum=MAX_DIAGRAMS_PER_ANALYSIS,
        )
        _validate_typed_tuple(
            "visual limitations",
            self.limitations,
            AnalysisLimitation,
            maximum=MAX_LIMITATIONS_PER_SCOPE,
        )
        if self.input_transform is not None and not isinstance(
            self.input_transform, VisualInputTransform
        ):
            raise ValueError("visual input transform is invalid")
        if (
            self.input_content_hash != self.source_content_hash
            and self.input_transform is None
        ):
            raise ValueError("transformed visual analysis requires transform metadata")
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(
                self.confidence, (int, float)
            ):
                raise ValueError("confidence must be a number")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class EnrichedSourceDocument:
    """A source document plus ordered, validated visual observations."""

    source: SourceDocument
    analysis_version: int
    analyses: tuple[VisualAnalysis, ...]
    limitations: tuple[AnalysisLimitation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceDocument):
            raise ValueError("source must be a SourceDocument")
        if (
            isinstance(self.analysis_version, bool)
            or not isinstance(self.analysis_version, int)
            or self.analysis_version != ENRICHMENT_ANALYSIS_VERSION
        ):
            raise ValueError(
                f"analysis version must be {ENRICHMENT_ANALYSIS_VERSION}"
            )
        _validate_typed_tuple(
            "visual analyses",
            self.analyses,
            VisualAnalysis,
            maximum=MAX_ANALYSES_PER_DOCUMENT,
        )
        _validate_typed_tuple(
            "document limitations",
            self.limitations,
            AnalysisLimitation,
            maximum=MAX_LIMITATIONS_PER_SCOPE,
        )

        visual_ids: set[str] = set()
        previous_order = 0
        for analysis in self.analyses:
            if analysis.visual_id in visual_ids:
                raise ValueError("visual analysis IDs must be unique")
            visual_ids.add(analysis.visual_id)
            if analysis.provenance.document != self.source.name:
                raise ValueError("visual analysis provenance must match source document")
            if analysis.provenance.order <= previous_order:
                raise ValueError("visual analyses must be ordered by source provenance")
            previous_order = analysis.provenance.order

            validate_visual_reference(
                self.source,
                visual_id=analysis.visual_id,
                source_asset_id=analysis.source_asset_id,
                provenance=analysis.provenance,
                input_kind=analysis.input_kind,
                source_content_hash=analysis.source_content_hash,
            )


def compute_content_hash(content: bytes) -> str:
    """Return the canonical SHA-256 digest for visual source bytes."""

    if not isinstance(content, bytes):
        raise ValueError("content must be bytes")
    return hashlib.sha256(content).hexdigest()


def build_visual_id(
    source: SourceDocument,
    *,
    input_kind: str,
    provenance: SourceProvenance,
    source_content_hash: str,
    source_asset_id: Optional[str],
) -> str:
    """Build a stable visual ID from immutable source observation identity.

    Provider-input bytes and transform details are deliberately excluded.  The
    same source evidence remains the same observation after safe resizing or
    re-encoding for a future provider.
    """

    if not isinstance(source, SourceDocument):
        raise ValueError("source must be a SourceDocument")
    if not isinstance(provenance, SourceProvenance):
        raise ValueError("provenance must be SourceProvenance")
    _validate_enum("input kind", input_kind, INPUT_KINDS)
    _validate_content_hash(source_content_hash)
    if source_asset_id is not None:
        _validate_identifier("source asset ID", source_asset_id, _ASSET_ID_PATTERN)
    payload = "\x1f".join(
        (
            source.name,
            source.source_format,
            input_kind,
            source_asset_id or "",
            provenance.document,
            str(provenance.order),
            str(provenance.position),
            str(provenance.page or ""),
            str(provenance.slide or ""),
            source_content_hash,
        )
    )
    return "visual-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def validate_visual_reference(
    source: SourceDocument,
    *,
    visual_id: str,
    source_asset_id: Optional[str],
    provenance: SourceProvenance,
    input_kind: str,
    source_content_hash: str,
) -> None:
    """Validate one deterministic visual reference against immutable source evidence.

    This shared validation deliberately has no provider, filesystem, or Web
    concerns.  It is used by both the persisted enrichment contract and future
    provider request contracts.
    """
    if not isinstance(source, SourceDocument):
        raise ValueError("source must be a SourceDocument")
    if not isinstance(provenance, SourceProvenance):
        raise ValueError("visual provenance must be SourceProvenance")
    _validate_identifier("visual ID", visual_id, _VISUAL_ID_PATTERN)
    if source_asset_id is not None:
        _validate_identifier("source asset ID", source_asset_id, _ASSET_ID_PATTERN)
    _validate_enum("input kind", input_kind, INPUT_KINDS)
    _validate_content_hash(source_content_hash)

    expected_id = build_visual_id(
        source,
        input_kind=input_kind,
        provenance=provenance,
        source_content_hash=source_content_hash,
        source_asset_id=source_asset_id,
    )
    if visual_id != expected_id:
        raise ValueError("visual ID does not match deterministic source reference")

    source_images = {
        element.asset_id: element
        for element in source.elements
        if isinstance(element, SourceImage)
    }
    source_boundaries = {
        element.provenance: element
        for element in source.elements
        if isinstance(element, SourceBoundary)
    }
    if input_kind == "source_image":
        _validate_source_image_reference(
            source_asset_id,
            provenance,
            source_content_hash,
            source_images,
        )
    elif input_kind == "page_render":
        if source.source_format != "pdf":
            raise ValueError("page_render requires a PDF source document")
        _validate_rendered_boundary_reference(
            source_asset_id,
            provenance,
            source_boundaries,
            expected_kind="page_break",
            expected_location="page",
        )
    else:
        if source.source_format != "pptx":
            raise ValueError("slide_render requires a PPTX source document")
        _validate_rendered_boundary_reference(
            source_asset_id,
            provenance,
            source_boundaries,
            expected_kind="slide_boundary",
            expected_location="slide",
        )


def _validate_source_image_reference(
    source_asset_id: Optional[str],
    provenance: SourceProvenance,
    source_content_hash: str,
    source_images: dict[str, SourceImage],
) -> None:
    if source_asset_id is None:
        raise ValueError("source_image analysis requires source_asset_id")
    source_image = source_images.get(source_asset_id)
    if source_image is None:
        raise ValueError("source asset ID is not declared by source document")
    if provenance != source_image.provenance:
        raise ValueError("source image analysis provenance does not match source asset")
    if source_content_hash != compute_content_hash(source_image.content):
        raise ValueError("source image analysis content hash does not match source asset")


def _validate_rendered_boundary_reference(
    source_asset_id: Optional[str],
    provenance: SourceProvenance,
    source_boundaries: dict[SourceProvenance, SourceBoundary],
    *,
    expected_kind: str,
    expected_location: str,
) -> None:
    if source_asset_id is not None:
        raise ValueError("rendered analysis must not declare source_asset_id")
    boundary = source_boundaries.get(provenance)
    if boundary is None or boundary.kind != expected_kind:
        raise ValueError("rendered analysis provenance must match its source boundary")
    if expected_location == "page":
        if provenance.page is None or provenance.slide is not None:
            raise ValueError("page_render provenance must identify a page only")
    elif provenance.slide is None or provenance.page is not None:
        raise ValueError("slide_render provenance must identify a slide only")


def _validate_enum(field: str, value: object, allowed: frozenset[str]) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"unsupported {field}")


def _validate_content_hash(value: object) -> None:
    if not isinstance(value, str) or not _CONTENT_HASH_PATTERN.fullmatch(value):
        raise ValueError("content hash must be a lowercase SHA-256 hex digest")


def _validate_identifier(field: str, value: object, pattern: re.Pattern[str]) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"invalid {field}")


def _validate_plain_text(
    field: str,
    value: object,
    *,
    maximum: int,
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds maximum length")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field} must not be empty")
    lowered = value.lower()
    if any(marker in lowered for marker in _UNSAFE_TEXT_MARKERS):
        raise ValueError(f"{field} must contain plain text only")


def _validate_tuple(field: str, value: object, *, maximum: int) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple")
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds maximum items")


def _validate_plain_text_tuple(
    field: str,
    value: object,
    *,
    maximum_items: int,
    maximum_text: int,
) -> None:
    _validate_tuple(field, value, maximum=maximum_items)
    assert isinstance(value, tuple)
    for item in value:
        _validate_plain_text(field, item, maximum=maximum_text)


def _validate_typed_tuple(
    field: str,
    value: object,
    expected_type: type,
    *,
    maximum: int,
) -> None:
    _validate_tuple(field, value, maximum=maximum)
    assert isinstance(value, tuple)
    if not all(isinstance(item, expected_type) for item in value):
        raise ValueError(f"{field} contain invalid values")
