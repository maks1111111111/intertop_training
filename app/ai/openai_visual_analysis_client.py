"""Isolated OpenAI Responses client for future visual source analysis.

The client accepts only already bounded in-memory ``VisualAnalysisRequest``
objects.  It is deliberately not wired into import, generation, or Web flows.
"""

from __future__ import annotations

import base64
import copy
import json
import time
from collections.abc import Callable, Mapping
from typing import Any, Optional

try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        OpenAI,
        RateLimitError,
    )
except ImportError:
    OpenAI = None  # type: ignore[misc, assignment]
    APIConnectionError = ()  # type: ignore[misc, assignment]
    APIStatusError = ()  # type: ignore[misc, assignment]
    APITimeoutError = ()  # type: ignore[misc, assignment]
    RateLimitError = ()  # type: ignore[misc, assignment]

from app.ai.visual_analysis_config import OpenAIVisualAnalysisConfig
from app.ai.visual_analysis_interfaces import (
    VisualAnalysisClient,
    VisualAnalysisRequest,
    VisualAnalysisResponse,
)
from app.ai.visual_analysis_prompt import build_visual_analysis_instruction
from app.content.visual_enrichment import (
    DIAGRAM_EDGE_KINDS,
    DIAGRAM_KINDS,
    DIAGRAM_NODE_KINDS,
    ENRICHMENT_ANALYSIS_VERSION,
    LIMITATION_CODES,
    UI_CONTROL_KINDS,
    AnalysisLimitation,
    DiagramEdge,
    DiagramNode,
    EnrichedSourceDocument,
    VisualAnalysis,
    VisualDiagram,
    VisualSection,
    VisualTable,
    VisualUIControl,
)


MAX_TOTAL_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.25
DEFAULT_VISUAL_IMAGE_DETAIL = "high"
VISUAL_IMAGE_DETAILS = frozenset({"auto", "high", "low", "original"})
_OUTPUT_SCHEMA_NAME = "visual_analysis_batch"


class VisualAnalysisClientError(RuntimeError):
    """Base error with deliberately non-sensitive messages."""


class VisualAnalysisTimeoutError(VisualAnalysisClientError):
    """The provider timed out after the bounded retry policy."""


class VisualAnalysisTransientError(VisualAnalysisClientError):
    """A transient provider failure exhausted the bounded retry policy."""


class VisualAnalysisResponseError(VisualAnalysisClientError):
    """The provider did not produce a locally valid structured response."""


class VisualAnalysisRefusalError(VisualAnalysisClientError):
    """The provider explicitly refused to analyze a requested image batch."""


class OpenAIVisualAnalysisClient(VisualAnalysisClient):
    """OpenAI-backed visual analysis with strict local response validation."""

    def __init__(
        self,
        config: OpenAIVisualAnalysisConfig,
        *,
        sdk_client: object | None = None,
        image_detail: str = DEFAULT_VISUAL_IMAGE_DETAIL,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(config, OpenAIVisualAnalysisConfig):
            raise ValueError("visual analysis configuration is invalid")
        if image_detail not in VISUAL_IMAGE_DETAILS:
            raise ValueError("unsupported visual image detail")
        if not callable(sleeper):
            raise ValueError("visual analysis sleeper must be callable")
        if sdk_client is None:
            if OpenAI is None:
                raise RuntimeError("OpenAI SDK is not installed.")
            sdk_client = OpenAI(
                api_key=config.api_key,
                max_retries=0,
                timeout=config.timeout_seconds,
            )
        self._client = sdk_client
        self._model = config.model
        self._image_detail = image_detail
        self._sleeper = sleeper

    def analyze(self, request: VisualAnalysisRequest) -> VisualAnalysisResponse:
        """Analyze one bounded request without exposing source identity to AI."""
        if not isinstance(request, VisualAnalysisRequest):
            raise ValueError("visual analysis request is invalid")
        response = self._create_response_with_retry(request)
        payload = _read_structured_payload(response)
        analyses_payload = _parse_batch_payload(payload, expected_count=len(request.inputs))

        analyses = tuple(
            _map_analysis_payload(payload_item, request.inputs[index])
            for index, payload_item in enumerate(analyses_payload)
        )
        try:
            enriched = EnrichedSourceDocument(
                source=request.source,
                analysis_version=ENRICHMENT_ANALYSIS_VERSION,
                analyses=analyses,
            )
        except (TypeError, ValueError) as error:
            raise VisualAnalysisResponseError(
                "Visual analysis provider response is invalid."
            ) from None
        return VisualAnalysisResponse(enriched_document=enriched)

    def _create_response_with_retry(self, request: VisualAnalysisRequest) -> object:
        for attempt in range(MAX_TOTAL_ATTEMPTS):
            try:
                return self._client.responses.create(**_build_response_request(
                    request,
                    model=self._model,
                    image_detail=self._image_detail,
                ))
            except Exception as error:
                retry_kind = _transient_error_kind(error)
                if retry_kind is None:
                    raise VisualAnalysisClientError(
                        "Visual analysis provider request failed."
                    ) from None
                if attempt + 1 == MAX_TOTAL_ATTEMPTS:
                    if retry_kind == "timeout":
                        raise VisualAnalysisTimeoutError(
                            "Visual analysis provider timed out."
                        ) from None
                    raise VisualAnalysisTransientError(
                        "Visual analysis provider is temporarily unavailable."
                    ) from None
                self._sleeper(RETRY_DELAY_SECONDS)
        raise AssertionError("bounded retry loop must return or raise")


def build_visual_analysis_response_schema() -> dict[str, object]:
    """Return a fresh strict JSON Schema for the provider's visible findings."""
    return copy.deepcopy(_VISUAL_ANALYSIS_RESPONSE_SCHEMA)


def _build_response_request(
    request: VisualAnalysisRequest,
    *,
    model: str,
    image_detail: str,
) -> dict[str, object]:
    content: list[dict[str, str]] = [
        {"type": "input_text", "text": build_visual_analysis_instruction()}
    ]
    for item in request.inputs:
        encoded = base64.b64encode(item.content).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{item.media_type};base64,{encoded}",
                "detail": image_detail,
            }
        )
    return {
        "model": model,
        "store": False,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": _OUTPUT_SCHEMA_NAME,
                "strict": True,
                "schema": build_visual_analysis_response_schema(),
            }
        },
    }


def _read_structured_payload(response: object) -> object:
    if _contains_refusal(response):
        raise VisualAnalysisRefusalError("Visual analysis provider refused the request.")
    output_text = _field(response, "output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        raise VisualAnalysisResponseError(
            "Visual analysis provider returned no structured output."
        )
    try:
        return json.loads(output_text)
    except (TypeError, json.JSONDecodeError):
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        ) from None


def _contains_refusal(response: object) -> bool:
    direct_refusal = _field(response, "refusal")
    if isinstance(direct_refusal, str) and direct_refusal:
        return True
    output = _field(response, "output")
    if not isinstance(output, list):
        return False
    for item in output:
        content = _field(item, "content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if _field(content_item, "type") == "refusal":
                return True
            refusal = _field(content_item, "refusal")
            if isinstance(refusal, str) and refusal:
                return True
    return False


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _transient_error_kind(error: Exception) -> Optional[str]:
    if isinstance(error, (TimeoutError, APITimeoutError)):
        return "timeout"
    if isinstance(error, (ConnectionError, APIConnectionError, RateLimitError)):
        return "transient"
    status_code = getattr(error, "status_code", None)
    if isinstance(error, APIStatusError) and isinstance(status_code, int):
        if 500 <= status_code <= 599:
            return "transient"
    return None


def _parse_batch_payload(payload: object, *, expected_count: int) -> list[object]:
    batch = _strict_object(payload, {"analyses"})
    analyses = _strict_list(batch["analyses"])
    if len(analyses) != expected_count:
        raise VisualAnalysisResponseError(
            "Visual analysis provider response has an unexpected analysis count."
        )
    return analyses


def _map_analysis_payload(payload: object, input_item: object) -> VisualAnalysis:
    from app.ai.visual_analysis_interfaces import VisualAnalysisInput

    if not isinstance(input_item, VisualAnalysisInput):
        raise AssertionError("validated request must contain visual analysis inputs")
    data = _strict_object(
        payload,
        {
            "description",
            "detected_text",
            "sections",
            "tables",
            "ui_controls",
            "diagrams",
            "confidence",
            "limitations",
        },
    )
    try:
        return VisualAnalysis(
            visual_id=input_item.visual_id,
            source_asset_id=input_item.source_asset_id,
            provenance=input_item.provenance,
            input_kind=input_item.input_kind,
            source_content_hash=input_item.source_content_hash,
            input_content_hash=input_item.input_content_hash,
            input_transform=input_item.transform,
            description=_string(data["description"]),
            detected_text=tuple(_string(item) for item in _strict_list(data["detected_text"])),
            sections=tuple(_parse_section(item) for item in _strict_list(data["sections"])),
            tables=tuple(_parse_table(item) for item in _strict_list(data["tables"])),
            ui_controls=tuple(_parse_ui_control(item) for item in _strict_list(data["ui_controls"])),
            diagrams=tuple(_parse_diagram(item) for item in _strict_list(data["diagrams"])),
            confidence=_confidence(data["confidence"]),
            limitations=tuple(
                _parse_limitation(item) for item in _strict_list(data["limitations"])
            ),
        )
    except (TypeError, ValueError, VisualAnalysisResponseError):
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        ) from None


def _parse_section(value: object) -> VisualSection:
    data = _strict_object(value, {"title", "text", "level"})
    return VisualSection(
        title=_string(data["title"]),
        text=_string(data["text"]),
        level=_integer(data["level"]),
    )


def _parse_table(value: object) -> VisualTable:
    data = _strict_object(value, {"columns", "rows"})
    columns = tuple(_string(item) for item in _strict_list(data["columns"]))
    rows = tuple(
        tuple(_string(cell) for cell in _strict_list(row))
        for row in _strict_list(data["rows"])
    )
    return VisualTable(columns=columns, rows=rows)


def _parse_ui_control(value: object) -> VisualUIControl:
    data = _strict_object(value, {"kind", "label", "state"})
    state = data["state"]
    if state is not None:
        state = _string(state)
    return VisualUIControl(kind=_string(data["kind"]), label=_string(data["label"]), state=state)


def _parse_diagram(value: object) -> VisualDiagram:
    data = _strict_object(value, {"kind", "summary", "nodes", "edges"})
    nodes = tuple(_parse_diagram_node(item) for item in _strict_list(data["nodes"]))
    edges = tuple(_parse_diagram_edge(item) for item in _strict_list(data["edges"]))
    return VisualDiagram(kind=_string(data["kind"]), summary=_string(data["summary"]), nodes=nodes, edges=edges)


def _parse_diagram_node(value: object) -> DiagramNode:
    data = _strict_object(value, {"node_id", "label", "kind"})
    return DiagramNode(
        node_id=_string(data["node_id"]),
        label=_string(data["label"]),
        kind=_string(data["kind"]),
    )


def _parse_diagram_edge(value: object) -> DiagramEdge:
    data = _strict_object(value, {"source_node_id", "target_node_id", "kind", "label"})
    label = data["label"]
    if label is not None:
        label = _string(label)
    return DiagramEdge(
        source_node_id=_string(data["source_node_id"]),
        target_node_id=_string(data["target_node_id"]),
        kind=_string(data["kind"]),
        label=label,
    )


def _parse_limitation(value: object) -> AnalysisLimitation:
    data = _strict_object(value, {"code", "detail"})
    return AnalysisLimitation(code=_string(data["code"]), detail=_string(data["detail"]))


def _strict_object(value: object, required: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != required:
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        )
    return value


def _strict_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        )
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        )
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        )
    return value


def _confidence(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VisualAnalysisResponseError(
            "Visual analysis provider response is invalid."
        )
    return float(value)


def _object_schema(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _enum_schema(allowed: frozenset[str]) -> dict[str, object]:
    return {"type": "string", "enum": sorted(allowed)}


_STRING = {"type": "string"}
_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
_VISUAL_ANALYSIS_RESPONSE_SCHEMA: dict[str, object] = _object_schema(
    {
        "analyses": {
            "type": "array",
            "items": {"$ref": "#/$defs/analysis"},
        }
    }
)
_VISUAL_ANALYSIS_RESPONSE_SCHEMA["$defs"] = {
    "analysis": _object_schema(
        {
            "description": _STRING,
            "detected_text": {"type": "array", "items": _STRING},
            "sections": {"type": "array", "items": {"$ref": "#/$defs/section"}},
            "tables": {"type": "array", "items": {"$ref": "#/$defs/table"}},
            "ui_controls": {"type": "array", "items": {"$ref": "#/$defs/ui_control"}},
            "diagrams": {"type": "array", "items": {"$ref": "#/$defs/diagram"}},
            "confidence": _NULLABLE_NUMBER,
            "limitations": {"type": "array", "items": {"$ref": "#/$defs/limitation"}},
        }
    ),
    "section": _object_schema({"title": _STRING, "text": _STRING, "level": {"type": "integer"}}),
    "table": _object_schema(
        {
            "columns": {"type": "array", "items": _STRING},
            "rows": {"type": "array", "items": {"type": "array", "items": _STRING}},
        }
    ),
    "ui_control": _object_schema(
        {"kind": _enum_schema(UI_CONTROL_KINDS), "label": _STRING, "state": _NULLABLE_STRING}
    ),
    "diagram": _object_schema(
        {
            "kind": _enum_schema(DIAGRAM_KINDS),
            "summary": _STRING,
            "nodes": {"type": "array", "items": {"$ref": "#/$defs/diagram_node"}},
            "edges": {"type": "array", "items": {"$ref": "#/$defs/diagram_edge"}},
        }
    ),
    "diagram_node": _object_schema(
        {"node_id": _STRING, "label": _STRING, "kind": _enum_schema(DIAGRAM_NODE_KINDS)}
    ),
    "diagram_edge": _object_schema(
        {
            "source_node_id": _STRING,
            "target_node_id": _STRING,
            "kind": _enum_schema(DIAGRAM_EDGE_KINDS),
            "label": _NULLABLE_STRING,
        }
    ),
    "limitation": _object_schema({"code": _enum_schema(LIMITATION_CODES), "detail": _STRING}),
}
