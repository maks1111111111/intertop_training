"""Mock-only tests for the isolated OpenAI visual-analysis client."""

from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ai.openai_visual_analysis_client import (
    DEFAULT_VISUAL_IMAGE_DETAIL,
    RETRY_DELAY_SECONDS,
    OpenAIVisualAnalysisClient,
    VisualAnalysisClientError,
    VisualAnalysisRefusalError,
    VisualAnalysisResponseError,
    VisualAnalysisTransientError,
)
from app.ai.visual_analysis_config import OpenAIVisualAnalysisConfig
from app.ai.visual_analysis_interfaces import (
    VisualAnalysisInput,
    VisualAnalysisRequest,
)
from app.content.importer import CourseImporter
from app.content.source_document import (
    SourceDocument,
    SourceProvenance,
    build_source_image,
)
from app.content.visual_enrichment import build_visual_id, compute_content_hash
from app.services.course_generation_flow_service import CourseGenerationFlowService
from app.services.course_generation_pipeline_service import CourseGenerationPipelineService


class OpenAIVisualAnalysisClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = OpenAIVisualAnalysisConfig(
            api_key="test-api-key",
            model="vision-model",
        )

    def test_responses_request_uses_only_in_memory_data_url_and_strict_schema(self) -> None:
        request = _request((b"first customer image",))
        sdk = _FakeSDK([_response(_valid_payload("Visible screen"))])
        client = OpenAIVisualAnalysisClient(self.config, sdk_client=sdk)

        client.analyze(request)

        call = sdk.responses.calls[0]
        self.assertEqual(call["model"], "vision-model")
        self.assertFalse(call["store"])
        content = call["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_text")
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], DEFAULT_VISUAL_IMAGE_DETAIL)
        self.assertEqual(
            content[1]["image_url"],
            "data:image/png;base64," + base64.b64encode(b"first customer image").decode("ascii"),
        )
        serialized = json.dumps(call, sort_keys=True)
        self.assertNotIn("/private/customer/guide.png", serialized)
        self.assertNotIn("source-", serialized)
        response_format = call["text"]["format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["strict"])
        self.assertFalse(response_format["schema"]["additionalProperties"])
        self.assertFalse(
            response_format["schema"]["$defs"]["analysis"]["additionalProperties"]
        )

    def test_multiple_inputs_preserve_order_and_identity_is_reconstructed_locally(self) -> None:
        request = _request((b"first", b"second"))
        sdk = _FakeSDK(
            [_response({"analyses": [_analysis("First"), _analysis("Second")]})]
        )
        response = OpenAIVisualAnalysisClient(self.config, sdk_client=sdk).analyze(request)

        analyses = response.enriched_document.analyses
        self.assertEqual([item.description for item in analyses], ["First", "Second"])
        for analysis, source_input in zip(analyses, request.inputs):
            self.assertEqual(analysis.visual_id, source_input.visual_id)
            self.assertEqual(analysis.source_asset_id, source_input.source_asset_id)
            self.assertEqual(analysis.provenance, source_input.provenance)
            self.assertEqual(analysis.source_content_hash, source_input.source_content_hash)
            self.assertEqual(analysis.input_content_hash, source_input.input_content_hash)

    def test_provider_cannot_override_source_identity(self) -> None:
        payload = _analysis("Visible")
        payload["visual_id"] = "visual-provider-overrides-identity"
        sdk = _FakeSDK([_response({"analyses": [payload]})])
        client = OpenAIVisualAnalysisClient(self.config, sdk_client=sdk)

        with self.assertRaises(VisualAnalysisResponseError):
            client.analyze(_request((b"image",)))

    def test_cardinality_must_match_inputs(self) -> None:
        sdk = _FakeSDK([_response({"analyses": [_analysis("Only one")]})])
        client = OpenAIVisualAnalysisClient(self.config, sdk_client=sdk)

        with self.assertRaisesRegex(VisualAnalysisResponseError, "analysis count"):
            client.analyze(_request((b"one", b"two")))

    def test_malformed_or_unknown_structured_fields_are_rejected(self) -> None:
        payload = _analysis("Visible")
        payload["unexpected"] = "not allowed"
        sdk = _FakeSDK([_response({"analyses": [payload]})])

        with self.assertRaises(VisualAnalysisResponseError):
            OpenAIVisualAnalysisClient(self.config, sdk_client=sdk).analyze(
                _request((b"image",))
            )

    def test_refusal_is_not_retried(self) -> None:
        sdk = _FakeSDK([SimpleNamespace(output_text=None, refusal="cannot assist", output=[])])
        client = OpenAIVisualAnalysisClient(self.config, sdk_client=sdk)

        with self.assertRaises(VisualAnalysisRefusalError):
            client.analyze(_request((b"image",)))

        self.assertEqual(len(sdk.responses.calls), 1)

    def test_timeout_is_retried_once_then_successfully_parsed(self) -> None:
        sleeps: list[float] = []
        sdk = _FakeSDK([TimeoutError("network delay"), _response(_valid_payload("Visible"))])
        client = OpenAIVisualAnalysisClient(
            self.config,
            sdk_client=sdk,
            sleeper=sleeps.append,
        )

        client.analyze(_request((b"image",)))

        self.assertEqual(len(sdk.responses.calls), 2)
        self.assertEqual(sleeps, [RETRY_DELAY_SECONDS])

    def test_transient_failure_has_at_most_two_total_attempts(self) -> None:
        sleeps: list[float] = []
        sdk = _FakeSDK([ConnectionError("temporary"), ConnectionError("temporary")])
        client = OpenAIVisualAnalysisClient(
            self.config,
            sdk_client=sdk,
            sleeper=sleeps.append,
        )

        with self.assertRaises(VisualAnalysisTransientError):
            client.analyze(_request((b"image",)))

        self.assertEqual(len(sdk.responses.calls), 2)
        self.assertEqual(sleeps, [RETRY_DELAY_SECONDS])

    def test_image_detail_is_an_isolated_client_policy(self) -> None:
        sdk = _FakeSDK([_response(_valid_payload("Visible"))])
        client = OpenAIVisualAnalysisClient(
            self.config,
            sdk_client=sdk,
            image_detail="auto",
        )

        client.analyze(_request((b"image",)))

        self.assertEqual(sdk.responses.calls[0]["input"][0]["content"][1]["detail"], "auto")

    def test_nontransient_provider_error_is_not_retried_or_leaked(self) -> None:
        secret = "customer-secret-content"
        sdk = _FakeSDK([ValueError(secret)])
        client = OpenAIVisualAnalysisClient(self.config, sdk_client=sdk)

        with self.assertRaises(VisualAnalysisClientError) as raised:
            client.analyze(_request((secret.encode("utf-8"),)))

        self.assertEqual(len(sdk.responses.calls), 1)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(base64.b64encode(secret.encode("utf-8")).decode("ascii"), str(raised.exception))

    def test_existing_import_and_generation_paths_do_not_call_visual_client(self) -> None:
        pipeline = MagicMock(spec=CourseGenerationPipelineService)
        flow = CourseGenerationFlowService(pipeline)
        reader = _TextReader()

        with patch.object(OpenAIVisualAnalysisClient, "analyze") as analyze:
            self.assertEqual(
                CourseImporter(readers={"pdf": reader}).read_source(Path("guide.pdf")),
                "source text",
            )
            flow.generate(MagicMock())

        analyze.assert_not_called()


class _FakeResponses:
    def __init__(self, actions: list[object]) -> None:
        self._actions = list(actions)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        action = self._actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


class _FakeSDK:
    def __init__(self, actions: list[object]) -> None:
        self.responses = _FakeResponses(actions)


class _TextReader:
    def read(self, path: Path) -> str:
        return "source text"


def _request(contents: tuple[bytes, ...]) -> VisualAnalysisRequest:
    elements = []
    inputs = []
    for index, content in enumerate(contents, start=1):
        provenance = SourceProvenance(
            document="guide.docx",
            order=index,
            position=index,
        )
        image = build_source_image(
            document="guide.docx",
            content=content,
            provenance=provenance,
        )
        elements.append(image)
    source = SourceDocument("guide.docx", "docx", tuple(elements))
    for image in elements:
        content_hash = compute_content_hash(image.content)
        inputs.append(
            VisualAnalysisInput(
                visual_id=build_visual_id(
                    source,
                    input_kind="source_image",
                    provenance=image.provenance,
                    source_content_hash=content_hash,
                    source_asset_id=image.asset_id,
                ),
                source_asset_id=image.asset_id,
                provenance=image.provenance,
                input_kind="source_image",
                source_content_hash=content_hash,
                input_content_hash=content_hash,
                media_type="image/png",
                content=image.content,
            )
        )
    return VisualAnalysisRequest(source=source, inputs=tuple(inputs))


def _response(payload: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(output_text=json.dumps(payload), output=[])


def _valid_payload(description: str) -> dict[str, object]:
    return {"analyses": [_analysis(description)]}


def _analysis(description: str) -> dict[str, object]:
    return {
        "description": description,
        "detected_text": ["Visible label"],
        "sections": [{"title": "Section", "text": "Body", "level": 2}],
        "tables": [{"columns": ["A"], "rows": [["B"]]}],
        "ui_controls": [{"kind": "button", "label": "Continue", "state": None}],
        "diagrams": [
            {
                "kind": "flow",
                "summary": "One visible step",
                "nodes": [{"node_id": "step-1", "label": "Start", "kind": "process_step"}],
                "edges": [],
            }
        ],
        "confidence": 0.8,
        "limitations": [],
    }


if __name__ == "__main__":
    unittest.main()
