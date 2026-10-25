"""Isolated OpenAI Responses client for future visual source analysis.

The client accepts only already bounded in-memory ``VisualAnalysisRequest``
objects.  It is deliberately not wired into import, generation, or Web flows.
"""

from __future__ import annotations

import base64
import copy
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    MAX_DESCRIPTION_LENGTH,
    MAX_DETECTED_TEXT_ITEMS,
    MAX_DIAGRAMS_PER_ANALYSIS,
    MAX_DIAGRAM_EDGES,
    MAX_DIAGRAM_NODES,
    MAX_SECTIONS_PER_ANALYSIS,
    MAX_TABLES_PER_ANALYSIS,
    MAX_UI_CONTROLS_PER_ANALYSIS,
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
_RESPONSE_ERROR_CODES = frozenset(
    {
        "missing_output",
        "malformed_json",
        "cardinality_mismatch",
        "schema_mapping_error",
        "local_validation_error",
    }
)
_SAFE_METADATA_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True)
class VisualAnalysisResponseMetadata:
    """Non-content response metadata retained when validation rejects output."""

    request_id: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class VisualAnalysisClientError(RuntimeError):
    """Base error with deliberately non-sensitive messages."""


class VisualAnalysisTimeoutError(VisualAnalysisClientError):
    """The provider timed out after the bounded retry policy."""


class VisualAnalysisTransientError(VisualAnalysisClientError):
    """A transient provider failure exhausted the bounded retry policy."""


class VisualAnalysisResponseError(VisualAnalysisClientError):
    """The provider did not produce a locally valid structured response."""

    def __init__(
        self,
        error_code: str,
        *,
        field_path: Optional[str] = None,
        validation_kind: Optional[str] = None,
        response_metadata: Optional[VisualAnalysisResponseMetadata] = None,
    ) -> None:
        if error_code not in _RESPONSE_ERROR_CODES:
            raise ValueError("unsupported visual analysis response error code")
        self.error_code = error_code
        self.field_path = field_path
        self.validation_kind = validation_kind
        self.response_metadata = response_metadata

        message = f"Visual analysis response rejected: {error_code}"
        if error_code == "cardinality_mismatch":
            message += " (analysis count)"
        if field_path is not None:
            message += f" at {field_path}"
        super().__init__(message + ".")

    def attach_response_metadata(
        self,
        response_metadata: VisualAnalysisResponseMetadata,
    ) -> None:
        """Attach technical metadata captured before parsing provider output."""
        if self.response_metadata is None:
            self.response_metadata = response_metadata


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
        response_metadata = _capture_response_metadata(response)
        try:
            payload = _read_structured_payload(response)
            analyses_payload = _parse_batch_payload(
                payload,
                expected_count=len(request.inputs),
            )
            analyses = tuple(
                _map_analysis_payload(payload_item, request.inputs[index], index=index)
                for index, payload_item in enumerate(analyses_payload)
            )
            enriched = EnrichedSourceDocument(
                source=request.source,
                analysis_version=ENRICHMENT_ANALYSIS_VERSION,
                analyses=analyses,
            )
        except VisualAnalysisResponseError as error:
            error.attach_response_metadata(response_metadata)
            raise
        except (TypeError, ValueError):
            raise _local_validation_error(
                "analyses",
                validation_kind="enriched_document",
                response_metadata=response_metadata,
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
        raise VisualAnalysisResponseError("missing_output")
    try:
        return json.loads(output_text)
    except (TypeError, json.JSONDecodeError):
        raise VisualAnalysisResponseError("malformed_json") from None


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


def _capture_response_metadata(response: object) -> VisualAnalysisResponseMetadata:
    """Extract only bounded technical metadata before output parsing begins."""
    usage = _field(response, "usage")
    input_details = _field(usage, "input_tokens_details")
    output_details = _field(usage, "output_tokens_details")
    return VisualAnalysisResponseMetadata(
        request_id=_safe_metadata_text(
            _field(response, "_request_id") or _field(response, "request_id")
        ),
        model=_safe_metadata_text(_field(response, "model")),
        input_tokens=_safe_metadata_integer(_field(usage, "input_tokens")),
        output_tokens=_safe_metadata_integer(_field(usage, "output_tokens")),
        reasoning_tokens=_safe_metadata_integer(_field(output_details, "reasoning_tokens")),
        cached_input_tokens=_safe_metadata_integer(_field(input_details, "cached_tokens")),
        total_tokens=_safe_metadata_integer(_field(usage, "total_tokens")),
    )


def _safe_metadata_text(value: object) -> Optional[str]:
    if not isinstance(value, str) or not _SAFE_METADATA_TEXT_PATTERN.fullmatch(value):
        return None
    return value


def _safe_metadata_integer(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


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
    batch = _strict_object(payload, {"analyses"}, path="response")
    analyses = _strict_list(batch["analyses"], path="analyses")
    if len(analyses) != expected_count:
        raise VisualAnalysisResponseError(
            "cardinality_mismatch",
            field_path="analyses",
            validation_kind="batch_cardinality",
        )
    return analyses


def _map_analysis_payload(payload: object, input_item: object, *, index: int) -> VisualAnalysis:
    from app.ai.visual_analysis_interfaces import VisualAnalysisInput

    if not isinstance(input_item, VisualAnalysisInput):
        raise AssertionError("validated request must contain visual analysis inputs")
    path = f"analyses[{index}]"
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
        path=path,
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
            description=_required_bounded_string(
                data["description"],
                path=f"{path}.description",
                maximum=MAX_DESCRIPTION_LENGTH,
            ),
            detected_text=tuple(
                _string(item, path=f"{path}.detected_text[{item_index}]")
                for item_index, item in enumerate(
                    _bounded_list(
                        data["detected_text"],
                        maximum=MAX_DETECTED_TEXT_ITEMS,
                        path=f"{path}.detected_text",
                    )
                )
            ),
            sections=tuple(
                _parse_section(item, path=f"{path}.sections[{item_index}]")
                for item_index, item in enumerate(
                    _bounded_list(
                        data["sections"],
                        maximum=MAX_SECTIONS_PER_ANALYSIS,
                        path=f"{path}.sections",
                    )
                )
            ),
            tables=tuple(
                _parse_table(item, path=f"{path}.tables[{item_index}]")
                for item_index, item in enumerate(
                    _bounded_list(
                        data["tables"],
                        maximum=MAX_TABLES_PER_ANALYSIS,
                        path=f"{path}.tables",
                    )
                )
            ),
            ui_controls=tuple(
                _parse_ui_control(item, path=f"{path}.ui_controls[{item_index}]")
                for item_index, item in enumerate(
                    _bounded_list(
                        data["ui_controls"],
                        maximum=MAX_UI_CONTROLS_PER_ANALYSIS,
                        path=f"{path}.ui_controls",
                    )
                )
            ),
            diagrams=tuple(
                _parse_diagram(item, path=f"{path}.diagrams[{item_index}]")
                for item_index, item in enumerate(
                    _bounded_list(
                        data["diagrams"],
                        maximum=MAX_DIAGRAMS_PER_ANALYSIS,
                        path=f"{path}.diagrams",
                    )
                )
            ),
            confidence=_confidence(data["confidence"], path=f"{path}.confidence"),
            limitations=tuple(
                _parse_limitation(item, path=f"{path}.limitations[{item_index}]")
                for item_index, item in enumerate(
                    _strict_list(data["limitations"], path=f"{path}.limitations")
                )
            ),
        )
    except VisualAnalysisResponseError:
        raise
    except (TypeError, ValueError):
        raise _local_validation_error(path, validation_kind="visual_analysis") from None


def _parse_section(value: object, *, path: str) -> VisualSection:
    data = _strict_object(value, {"title", "text", "level"}, path=path)
    return _construct_local(
        lambda: VisualSection(
            title=_string(data["title"], path=f"{path}.title"),
            text=_string(data["text"], path=f"{path}.text"),
            level=_integer(data["level"], path=f"{path}.level"),
        ),
        path=path,
        validation_kind="section",
    )


def _parse_table(value: object, *, path: str) -> VisualTable:
    data = _strict_object(value, {"columns", "rows"}, path=path)
    columns_data = _strict_list(data["columns"], path=f"{path}.columns")
    if not columns_data:
        raise _local_validation_error(
            f"{path}.columns",
            validation_kind="table_columns",
        )
    columns = tuple(
        _string(item, path=f"{path}.columns[{index}]")
        for index, item in enumerate(columns_data)
    )
    rows_data = _strict_list(data["rows"], path=f"{path}.rows")
    rows: list[tuple[str, ...]] = []
    for row_index, row_data in enumerate(rows_data):
        row = _strict_list(row_data, path=f"{path}.rows[{row_index}]")
        if len(row) != len(columns):
            raise _local_validation_error(
                f"{path}.rows[{row_index}]",
                validation_kind="table_row_width",
            )
        rows.append(
            tuple(
                _string(cell, path=f"{path}.rows[{row_index}][{cell_index}]")
                for cell_index, cell in enumerate(row)
            )
        )
    return _construct_local(
        lambda: VisualTable(columns=columns, rows=tuple(rows)),
        path=path,
        validation_kind="table",
    )


def _parse_ui_control(value: object, *, path: str) -> VisualUIControl:
    data = _strict_object(value, {"kind", "label", "state"}, path=path)
    state = data["state"]
    if state is not None:
        state = _string(state, path=f"{path}.state")
    return _construct_local(
        lambda: VisualUIControl(
            kind=_string(data["kind"], path=f"{path}.kind"),
            label=_string(data["label"], path=f"{path}.label"),
            state=state,
        ),
        path=path,
        validation_kind="ui_control",
    )


def _parse_diagram(value: object, *, path: str) -> VisualDiagram:
    data = _strict_object(value, {"kind", "summary", "nodes", "edges"}, path=path)
    nodes_data = _bounded_list(
        data["nodes"],
        maximum=MAX_DIAGRAM_NODES,
        path=f"{path}.nodes",
    )
    if not nodes_data:
        raise _local_validation_error(f"{path}.nodes", validation_kind="diagram_nodes")
    nodes = tuple(
        _parse_diagram_node(item, path=f"{path}.nodes[{index}]")
        for index, item in enumerate(nodes_data)
    )
    node_ids = {node.node_id for node in nodes}
    if len(node_ids) != len(nodes):
        raise _local_validation_error(f"{path}.nodes", validation_kind="diagram_node_ids")
    edges_data = _bounded_list(
        data["edges"],
        maximum=MAX_DIAGRAM_EDGES,
        path=f"{path}.edges",
    )
    edges = tuple(
        _parse_diagram_edge(item, path=f"{path}.edges[{index}]")
        for index, item in enumerate(edges_data)
    )
    for index, edge in enumerate(edges):
        if edge.source_node_id not in node_ids:
            raise _local_validation_error(
                f"{path}.edges[{index}].source_node_id",
                validation_kind="diagram_edge_reference",
            )
        if edge.target_node_id not in node_ids:
            raise _local_validation_error(
                f"{path}.edges[{index}].target_node_id",
                validation_kind="diagram_edge_reference",
            )
    return _construct_local(
        lambda: VisualDiagram(
            kind=_string(data["kind"], path=f"{path}.kind"),
            summary=_string(data["summary"], path=f"{path}.summary"),
            nodes=nodes,
            edges=edges,
        ),
        path=path,
        validation_kind="diagram",
    )


def _parse_diagram_node(value: object, *, path: str) -> DiagramNode:
    data = _strict_object(value, {"node_id", "label", "kind"}, path=path)
    return _construct_local(
        lambda: DiagramNode(
            node_id=_string(data["node_id"], path=f"{path}.node_id"),
            label=_string(data["label"], path=f"{path}.label"),
            kind=_string(data["kind"], path=f"{path}.kind"),
        ),
        path=path,
        validation_kind="diagram_node",
    )


def _parse_diagram_edge(value: object, *, path: str) -> DiagramEdge:
    data = _strict_object(
        value,
        {"source_node_id", "target_node_id", "kind", "label"},
        path=path,
    )
    label = data["label"]
    if label is not None:
        label = _string(label, path=f"{path}.label")
    source_node_id = _string(data["source_node_id"], path=f"{path}.source_node_id")
    target_node_id = _string(data["target_node_id"], path=f"{path}.target_node_id")
    if source_node_id == target_node_id:
        raise _local_validation_error(
            f"{path}.target_node_id",
            validation_kind="diagram_self_edge",
        )
    return _construct_local(
        lambda: DiagramEdge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            kind=_string(data["kind"], path=f"{path}.kind"),
            label=label,
        ),
        path=path,
        validation_kind="diagram_edge",
    )


def _parse_limitation(value: object, *, path: str) -> AnalysisLimitation:
    data = _strict_object(value, {"code", "detail"}, path=path)
    return _construct_local(
        lambda: AnalysisLimitation(
            code=_string(data["code"], path=f"{path}.code"),
            detail=_string(data["detail"], path=f"{path}.detail"),
        ),
        path=path,
        validation_kind="limitation",
    )


def _strict_object(value: object, required: set[str], *, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != required:
        raise VisualAnalysisResponseError(
            "schema_mapping_error",
            field_path=path,
            validation_kind="object_shape",
        )
    return value


def _strict_list(value: object, *, path: str) -> list[object]:
    if not isinstance(value, list):
        raise VisualAnalysisResponseError(
            "schema_mapping_error",
            field_path=path,
            validation_kind="array_shape",
        )
    return value


def _bounded_list(value: object, *, maximum: int, path: str) -> list[object]:
    values = _strict_list(value, path=path)
    if len(values) > maximum:
        raise _local_validation_error(path, validation_kind="collection_limit")
    return values


def _string(value: object, *, path: str) -> str:
    if not isinstance(value, str):
        raise VisualAnalysisResponseError(
            "schema_mapping_error",
            field_path=path,
            validation_kind="string_type",
        )
    return value


def _required_bounded_string(value: object, *, path: str, maximum: int) -> str:
    text = _string(value, path=path)
    if not text.strip() or len(text) > maximum:
        raise _local_validation_error(path, validation_kind="string_constraints")
    return text


def _integer(value: object, *, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VisualAnalysisResponseError(
            "schema_mapping_error",
            field_path=path,
            validation_kind="integer_type",
        )
    return value


def _confidence(value: object, *, path: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VisualAnalysisResponseError(
            "schema_mapping_error",
            field_path=path,
            validation_kind="confidence_type",
        )
    if not 0 <= float(value) <= 1:
        raise _local_validation_error(path, validation_kind="confidence_range")
    return float(value)


def _construct_local(
    factory: Callable[[], Any],
    *,
    path: str,
    validation_kind: str,
) -> Any:
    try:
        return factory()
    except (TypeError, ValueError):
        raise _local_validation_error(path, validation_kind=validation_kind) from None


def _local_validation_error(
    field_path: str,
    *,
    validation_kind: str,
    response_metadata: Optional[VisualAnalysisResponseMetadata] = None,
) -> VisualAnalysisResponseError:
    return VisualAnalysisResponseError(
        "local_validation_error",
        field_path=field_path,
        validation_kind=validation_kind,
        response_metadata=response_metadata,
    )


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
