"""Tests for provider-neutral visual analysis interfaces."""

from __future__ import annotations

import unittest

from app.ai.visual_analysis_interfaces import (
    MAX_VISUAL_INPUT_BYTES,
    MAX_VISUAL_INPUTS_PER_REQUEST,
    FakeVisualAnalysisClient,
    VisualAnalysisInput,
    VisualAnalysisRequest,
    VisualAnalysisResponse,
    VisualInputTransform,
)
from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceProvenance,
    build_source_image,
)
from app.content.visual_enrichment import (
    EnrichedSourceDocument,
    build_visual_id,
    compute_content_hash,
)


class VisualAnalysisInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provenance = SourceProvenance(
            document="guide.pdf", order=1, position=0, page=1
        )
        self.source = SourceDocument(
            name="guide.pdf",
            source_format="pdf",
            elements=(SourceBoundary("page_break", self.provenance),),
        )
        self.source_content = b"canonical rendered page"
        self.input_content = b"provider sized page"
        self.source_hash = compute_content_hash(self.source_content)
        self.input_hash = compute_content_hash(self.input_content)
        self.visual_id = build_visual_id(
            self.source,
            input_kind="page_render",
            provenance=self.provenance,
            source_content_hash=self.source_hash,
            source_asset_id=None,
        )

    def _page_input(self, *, transform: VisualInputTransform | None = None) -> VisualAnalysisInput:
        return VisualAnalysisInput(
            visual_id=self.visual_id,
            source_asset_id=None,
            provenance=self.provenance,
            input_kind="page_render",
            source_content_hash=self.source_hash,
            input_content_hash=self.input_hash,
            media_type="image/png",
            content=self.input_content,
            transform=transform,
        )

    def test_fake_records_request_without_network(self) -> None:
        transform = VisualInputTransform(1, "contain", 1600, "image/png")
        request = VisualAnalysisRequest(
            source=self.source,
            inputs=(self._page_input(transform=transform),),
        )
        response = VisualAnalysisResponse(EnrichedSourceDocument(self.source, 1, ()))
        client = FakeVisualAnalysisClient(response)

        self.assertIs(client.analyze(request), response)
        self.assertEqual(client.requests, [request])

    def test_transformed_source_image_keeps_original_source_hash(self) -> None:
        source_content = b"original screenshot bytes"
        input_content = b"re-encoded screenshot bytes"
        provenance = SourceProvenance(
            document="guide.docx", order=1, position=1
        )
        image = build_source_image(
            document="guide.docx", content=source_content, provenance=provenance
        )
        source = SourceDocument("guide.docx", "docx", (image,))
        source_hash = compute_content_hash(source_content)
        input_hash = compute_content_hash(input_content)
        visual_id = build_visual_id(
            source,
            input_kind="source_image",
            provenance=provenance,
            source_content_hash=source_hash,
            source_asset_id=image.asset_id,
        )
        request = VisualAnalysisRequest(
            source=source,
            inputs=(
                VisualAnalysisInput(
                    visual_id=visual_id,
                    source_asset_id=image.asset_id,
                    provenance=provenance,
                    input_kind="source_image",
                    source_content_hash=source_hash,
                    input_content_hash=input_hash,
                    media_type="image/jpeg",
                    content=input_content,
                    transform=VisualInputTransform(1, "none", None, "image/jpeg"),
                ),
            ),
        )

        item = request.inputs[0]
        self.assertEqual(item.source_content_hash, source_hash)
        self.assertEqual(item.input_content_hash, input_hash)
        self.assertNotEqual(item.source_content_hash, item.input_content_hash)

    def test_transformed_bytes_require_transform_metadata(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires transform"):
            self._page_input()

    def test_request_rejects_unsupported_media_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "media type"):
            VisualAnalysisInput(
                visual_id=self.visual_id,
                source_asset_id=None,
                provenance=self.provenance,
                input_kind="page_render",
                source_content_hash=self.source_hash,
                input_content_hash=self.input_hash,
                media_type="image/gif",
                content=self.input_content,
                transform=VisualInputTransform(1, "contain", 1600, "image/png"),
            )

    def test_input_byte_limit_remains_bounded(self) -> None:
        content = b"x" * (MAX_VISUAL_INPUT_BYTES + 1)
        content_hash = compute_content_hash(content)
        visual_id = build_visual_id(
            self.source,
            input_kind="page_render",
            provenance=self.provenance,
            source_content_hash=content_hash,
            source_asset_id=None,
        )

        with self.assertRaisesRegex(ValueError, "maximum bytes"):
            VisualAnalysisInput(
                visual_id=visual_id,
                source_asset_id=None,
                provenance=self.provenance,
                input_kind="page_render",
                source_content_hash=content_hash,
                input_content_hash=content_hash,
                media_type="image/png",
                content=content,
            )

    def test_request_count_limit_remains_bounded(self) -> None:
        source, inputs = _source_and_valid_image_inputs(MAX_VISUAL_INPUTS_PER_REQUEST + 1)

        with self.assertRaisesRegex(ValueError, "maximum inputs"):
            VisualAnalysisRequest(source=source, inputs=inputs)


def _source_and_valid_image_inputs(
    count: int,
) -> tuple[SourceDocument, tuple[VisualAnalysisInput, ...]]:
    elements = []
    for index in range(1, count + 1):
        provenance = SourceProvenance(
            document="batch.docx", order=index, position=index
        )
        elements.append(
            build_source_image(
                document="batch.docx",
                content=f"image-{index}".encode("utf-8"),
                provenance=provenance,
            )
        )
    source = SourceDocument("batch.docx", "docx", tuple(elements))
    inputs = []
    for image in elements:
        source_hash = compute_content_hash(image.content)
        inputs.append(
            VisualAnalysisInput(
                visual_id=build_visual_id(
                    source,
                    input_kind="source_image",
                    provenance=image.provenance,
                    source_content_hash=source_hash,
                    source_asset_id=image.asset_id,
                ),
                source_asset_id=image.asset_id,
                provenance=image.provenance,
                input_kind="source_image",
                source_content_hash=source_hash,
                input_content_hash=source_hash,
                media_type="image/jpeg",
                content=image.content,
            )
        )
    return source, tuple(inputs)


if __name__ == "__main__":
    unittest.main()
